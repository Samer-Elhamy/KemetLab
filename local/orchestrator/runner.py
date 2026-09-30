#!/usr/bin/env python3
"""One-iteration local FSM driver with Kimi swarm pipelining."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from local.llm.ollama_client import generate_fsm_json, unload_model_from_vram
from local.memory.retrieve import build_prompt
from local.memory import GraphStore
from local.memory import blocks as block_mod
from local.memory import ingest as ingest_mod
from local.memory import shard_commit
from local.orchestrator import agent_tracker, critical_path, fsm, promotion, shards


def _log_session(focus_root: Path, record: dict) -> None:
    path = focus_root / "logs" / "sessions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _log_experiment(focus_root: Path, record: dict) -> None:
    path = focus_root / "logs" / "experiments.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _update_job_phase(focus_root: Path, cycle: int, agent_id: str, detail: str) -> None:
    from local.dashboard.job_status import read_job_status, write_job_status

    st = read_job_status(focus_root)
    st["current_phase"] = detail
    st["current_agent"] = agent_id
    st["current_cycle"] = cycle
    write_job_status(focus_root, st)


def _run_train(focus_root: Path, params: dict) -> dict:
    exec_mode = os.environ.get("AUTOSCIENTISTS_EXEC_MODE", "local").strip().lower()
    no_local_fallback = os.environ.get(
        "AUTOSCIENTISTS_NO_LOCAL_FALLBACK", ""
    ).strip().lower() in ("1", "true", "yes")
    if exec_mode == "kaggle":
        from local.orchestrator.kaggle_runner import run_train_kaggle

        competition = (
            os.environ.get("AUTOSCIENTISTS_COMPETITION")
            or os.environ.get("KAGGLE_COMPETITION")
            or "playground-series-s6e9"
        ).strip()
        timeout = int(os.environ.get("AUTOSCIENTISTS_KAGGLE_TIMEOUT", "7200"))
        try:
            print(
                f"[runner] Kaggle remote exec competition={competition} timeout={timeout}s",
                flush=True,
            )
            return run_train_kaggle(
                focus_root,
                params,
                timeout=timeout,
                competition=competition,
            )
        except Exception as e:
            if no_local_fallback or exec_mode == "kaggle":
                # Never burn local GPU/CPU on full training when Kaggle mode is requested.
                raise RuntimeError(
                    f"Remote Kaggle execution failed (local fallback disabled): {e}"
                ) from e
            print(
                f"[runner] Remote Kaggle execution failed: {e}. Falling back to local execution.",
                file=sys.stderr,
            )

    train_py = focus_root / "task" / "repo" / "train.py"
    if not train_py.exists():
        train_py = focus_root / "repo" / "train.py"
    env = {**dict(os.environ), "SMOKE_LR": str(params.get("lr", 0.05))}
    env["SMOKE_HIDDEN"] = str(params.get("hidden_dim", 16))
    env["SMOKE_STEPS"] = str(params.get("steps", 30))
    for k, v in params.items():
        env[str(k).upper()] = str(v)

    py_exe = "C:/Users/Samer/kaggle/.venv/Scripts/python.exe"
    if not Path(py_exe).exists():
        py_exe = sys.executable

    proc = subprocess.run(
        [py_exe, str(train_py)],
        cwd=str(train_py.parent),
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"train.py failed: {proc.stderr[:500]}")
    for line in proc.stdout.splitlines():
        if line.strip().startswith("{"):
            return json.loads(line.strip())
    raise RuntimeError(f"No JSON metric in train output: {proc.stdout[:300]}")


def run_iteration(focus_root: Path, cycle: int = 1) -> dict:
    focus_root = Path(focus_root).resolve()
    import os

    if os.environ.get("LOCAL_TEAM_MODE", "1").lower() not in ("0", "false", "no"):
        from local.orchestrator.team_runner import run_team_iteration

        return run_team_iteration(focus_root, cycle=cycle)

    task_md = (focus_root / "task" / "TASK.md").read_text(encoding="utf-8")
    store = GraphStore(focus_root)
    try:
        return _run_iteration_inner(focus_root, store, task_md, cycle)
    finally:
        store.close()


def _run_iteration_inner(
    focus_root: Path,
    store: GraphStore,
    task_md: str,
    cycle: int,
) -> dict:
    agent_tracker.set_agent(
        focus_root, "orchestrator", "working", f"بدء الدورة {cycle}", cycle=cycle
    )
    _update_job_phase(focus_root, cycle, "orchestrator", "بدء الدورة")

    block = block_mod.open_block()
    champ_before = promotion.load_champion_json(focus_root).get("val_loss", float("inf"))

    # Phase 1 — CPU: shard accumulation + critical path prep
    agent_tracker.set_all_idle_except(
        focus_root, "shard_cpu", "تحليل Graph-RAG والمسار الحرج", cycle
    )
    _update_job_phase(focus_root, cycle, "shard_cpu", "تحليل Graph-RAG")
    shard_propose = shards.create_shard("propose", task_md[:2000])
    shard_review = shards.create_shard("peer_review")
    shard_ingest = shards.create_shard("ingest")

    cp = critical_path.decompose_and_run(
        [
            ("verify_graph", lambda: store.nodes_by_kind("Champion", limit=1)),
            ("shard_propose_buf", lambda: shard_propose.append("task loaded")),
        ]
    )
    _log_session(
        focus_root,
        {
            "cycle": cycle,
            "phase": "shard_accumulation",
            "critical_path": cp.__dict__,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Phase 2 — GPU: reasoning burst (Propose)
    print("[FSM] state=Propose")
    agent_tracker.set_all_idle_except(
        focus_root, "propose", "توليد اقتراح معاملات (qwen35custom)", cycle
    )
    _update_job_phase(focus_root, cycle, "propose", "Propose — qwen35custom")
    proposal = fsm.run_propose(store, task_md, focus_root=focus_root, cycle=cycle)
    if proposal.get("status") == "error":
        print(f"[FSM] Propose failed: {proposal.get('reason')}")
        agent_tracker.set_agent(
            focus_root, "propose", "error", proposal.get("reason", "error")[:200], cycle=cycle
        )
        return {"state": "error", "outcome": "ERROR", "reason": proposal.get("reason")}
    agent_tracker.set_agent(
        focus_root,
        "propose",
        "done",
        f"params={proposal.get('params', {})}",
        cycle=cycle,
    )
    shard_propose.append(json.dumps(proposal))
    syn_p = shards.synthesize_shard_light(shard_propose)
    shard_commit.commit_shard_synthesis(store, shard_propose.shard_id, "propose", syn_p)

    print("[FSM] state=PeerReview")
    agent_tracker.set_all_idle_except(
        focus_root, "peer_review", "مراجعة الاقتراح", cycle
    )
    _update_job_phase(focus_root, cycle, "peer_review", "PeerReview")
    review = fsm.run_peer_review(store, task_md, proposal)
    shard_review.append(json.dumps(review))
    syn_r = shards.synthesize_shard_light(shard_review)
    shard_commit.commit_shard_synthesis(store, shard_review.shard_id, "peer_review", syn_r)

    if not review.get("approved", False):
        print("[FSM] PeerReview rejected — skipping Execute")
        agent_tracker.set_agent(
            focus_root,
            "peer_review",
            "done",
            "مرفوض — " + "; ".join(review.get("reasons", [])[:2])[:180],
            cycle=cycle,
        )
        agent_tracker.set_agent(focus_root, "execute", "skipped", "لم تُوافق المراجعة", cycle=cycle)
        block.mark_state("PeerReview")
        summary = {
            "outcome": "DISCARD",
            "key_findings": review.get("reasons", ["rejected"]),
        }
        block_mod.close_block(store, block, summary, champ_before, champ_before)
        agent_tracker.mark_cycle_done(focus_root, cycle, "DISCARD — رفض المراجعة")
        return {"state": "UpdateGraph", "outcome": "DISCARD", "approved": False}

    agent_tracker.set_agent(focus_root, "peer_review", "done", "موافق — انتقل للتنفيذ", cycle=cycle)

    # Phase 2b — VRAM purge
    unload_model_from_vram()

    # Phase 3 — Sandbox training
    print("[FSM] state=Execute")
    agent_tracker.set_all_idle_except(
        focus_root, "execute", "تشغيل train.py", cycle
    )
    _update_job_phase(focus_root, cycle, "execute", "Execute — train.py")
    if cp.serial_collapse:
        print("[FSM] SERIAL_COLLAPSE flagged — Tier-1 refactor nudge via qwen35custom")
        system, prompt = build_prompt("propose", store, task_md)
        refined = generate_fsm_json(
            prompt, system, tier="auto", fsm_state="propose", force_heavy=True
        )
        if refined.get("params"):
            proposal["params"] = refined["params"]
        else:
            params = proposal.get("params", {})
            params["lr"] = float(params.get("lr", 0.05)) * 0.9
            proposal["params"] = params

    result = _run_train(focus_root, proposal.get("params", {}))
    val_loss = float(result["val_loss"])
    agent_tracker.set_agent(
        focus_root, "execute", "done", f"val_loss={val_loss:.6f}", cycle=cycle
    )
    champ = promotion.load_champion_json(focus_root)
    improved = val_loss < champ.get("val_loss", float("inf"))
    outcome = "KEEP" if improved else "DISCARD"

    print("[FSM] state=IngestResult")
    agent_tracker.set_all_idle_except(
        focus_root, "ingest", "تسجيل النتيجة في الذاكرة", cycle
    )
    _update_job_phase(focus_root, cycle, "ingest", "Ingest")
    shard_ingest.append(json.dumps(result))
    syn_i = shards.synthesize_shard_light(shard_ingest)
    shard_commit.commit_shard_synthesis(store, shard_ingest.shard_id, "ingest", syn_i)

    exp_id = ingest_mod.ingest_experiment(
        store,
        proposal,
        {"val_loss": val_loss, "outcome": outcome, "exp_id": result.get("exp_id", "smoke")},
    )
    ingest_mod.ensure_champion(store, val_loss, proposal.get("params", {}))
    promotion.promote_if_improved(
        focus_root,
        val_loss,
        proposal.get("params", {}),
        focus_root / "task" / "repo" / "train.py",
    )

    champ_after = promotion.load_champion_json(focus_root).get("val_loss", val_loss)
    agent_tracker.set_agent(focus_root, "ingest", "done", f"outcome={outcome}", cycle=cycle)
    print("[FSM] state=UpdateGraph")
    agent_tracker.set_all_idle_except(
        focus_root, "graph", "تحديث Graph-RAG والـ champion", cycle
    )
    summary = {
        "outcome": outcome,
        "key_findings": [f"val_loss={val_loss}", f"exp_id={exp_id}"],
        "dead_ends_added": [] if improved else [f"params={proposal.get('params')}"],
    }
    block.mark_state("Execute")
    block.mark_state("IngestResult")
    block_mod.close_block(store, block, summary, champ_before, champ_after)

    exp_record = {
        "cycle": cycle,
        "exp_id": exp_id,
        "val_loss": val_loss,
        "outcome": outcome,
        "params": proposal.get("params"),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _log_experiment(focus_root, exp_record)
    _log_session(
        focus_root,
        {
            "cycle": cycle,
            "phase": "complete",
            "serial_collapse": cp.serial_collapse,
            "promise_received": True,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )

    print("[FSM] state=UpdateGraph complete")
    agent_tracker.set_agent(focus_root, "graph", "done", f"champion={champ_after}", cycle=cycle)
    agent_tracker.mark_cycle_done(
        focus_root, cycle, f"اكتملت — {outcome} val_loss={val_loss:.6f}"
    )
    return {"state": "done", "outcome": outcome, "val_loss": val_loss}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one local FSM iteration.")
    parser.add_argument("--focus-root", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--cycle-start", type=int, default=1)
    args = parser.parse_args()

    for i in range(args.max_cycles):
        cycle = args.cycle_start + i
        print(f"\n{'=' * 60}\nCYCLE {cycle}\n{'=' * 60}")
        run_iteration(args.focus_root, cycle=cycle)


if __name__ == "__main__":
    main()
