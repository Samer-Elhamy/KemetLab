#!/usr/bin/env python3
"""Meta FSM: Qwen agents patch experiments repo; benchmark resource_score."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.llm.ollama_client import generate_fsm_json, unload_model_from_vram
from local.memory import GraphStore, blocks as block_mod, ingest as ingest_mod, shard_commit
from local.memory.retrieve import build_prompt, task_spec_excerpt
from local.orchestrator import agent_tracker, fsm, promotion, shards
from local.orchestrator.meta_patch import apply_changes, target_repo
from local.orchestrator.runner import _log_experiment, _log_session, _update_job_phase


def _load_schema(name: str) -> dict:
    return json.loads((_REPO / "local" / "schemas" / f"{name}.json").read_text(encoding="utf-8"))


def _validate(name: str, data: dict) -> None:
    import jsonschema

    jsonschema.validate(instance=data, schema=_load_schema(name))


def _research_context() -> str:
    doc = _REPO / "docs" / "META_LOCAL_RESEARCH.md"
    if doc.exists():
        return task_spec_excerpt(doc.read_text(encoding="utf-8"), max_tokens=800)
    return ""


def _build_meta_propose_prompt(store: GraphStore, task_md: str) -> tuple[str, str]:
    system = (_REPO / "local" / "prompts" / "meta_propose.txt").read_text(encoding="utf-8")
    champ = store.get_node("champion")
    ctx = _research_context()
    body = f"## Target repo\n{target_repo()}\n\n## Research\n{ctx}\n\n## Champion\n{champ}\n"
    user = "## TASK\n" + task_spec_excerpt(task_md) + "\n\n" + body
    return system, user


def run_meta_propose(store: GraphStore, task_md: str, cycle: int = 1) -> dict:
    system, prompt = _build_meta_propose_prompt(store, task_md)
    raw = generate_fsm_json(prompt, system, tier="heavy", fsm_state="propose", force_heavy=True)
    if raw.get("status") == "error":
        import os
        from local.orchestrator.meta_patch_queue import pick_patch

        if os.environ.get("META_GUIDED_ON_LLM_FAIL", "1").lower() not in ("0", "false", "no"):
            guided = pick_patch(cycle)
            if guided.get("status") != "error":
                print("[MetaFSM] Qwen unavailable — using research patch queue")
                return guided
        return raw
    if "changes" not in raw and "params" in raw:
        return {"status": "error", "reason": "got hyperparam proposal instead of meta changes"}
    _validate("meta_proposal", raw)
    return raw


def run_meta_peer_review(store: GraphStore, task_md: str, proposal: dict) -> dict:
    system = (_REPO / "local" / "prompts" / "meta_review.txt").read_text(encoding="utf-8")
    prompt = (
        f"Review this patch proposal for {target_repo()}:\n"
        + json.dumps(proposal, ensure_ascii=False, indent=2)
    )
    raw = generate_fsm_json(prompt, system, tier="heavy", fsm_state="peer_review")
    from local.llm.normalize import normalize_peer_review

    return normalize_peer_review(raw)


def _run_benchmark(focus_root: Path) -> dict:
    bench = focus_root / "task" / "repo" / "benchmark.py"
    if not bench.exists():
        bench = _REPO / "task-meta-local" / "repo" / "benchmark.py"
    env = {**os.environ, "META_EXP_ID": f"meta_{int(time.time())}", "LOCAL_ONLY": "1"}
    env.setdefault("META_BENCHMARK_SKIP_OLLAMA", "1")
    proc = subprocess.run(
        [sys.executable, str(bench)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(bench.parent),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[:400] or proc.stdout[:400])
    for line in proc.stdout.splitlines():
        if line.strip().startswith("{"):
            return json.loads(line.strip())
    raise RuntimeError("no benchmark JSON")


def run_meta_iteration(focus_root: Path, cycle: int = 1) -> dict:
    focus_root = Path(focus_root).resolve()
    target_repo()  # validate env
    task_md = (focus_root / "task" / "TASK.md").read_text(encoding="utf-8")
    store = GraphStore(focus_root)
    try:
        return _run_meta_inner(focus_root, store, task_md, cycle)
    finally:
        store.close()


def _run_meta_inner(
    focus_root: Path,
    store: GraphStore,
    task_md: str,
    cycle: int,
) -> dict:
    agent_tracker.set_agent(focus_root, "orchestrator", "working", f"meta cycle {cycle}", cycle=cycle)
    _update_job_phase(focus_root, cycle, "orchestrator", f"Meta cycle {cycle}")
    champ_before = promotion.load_champion_json(focus_root).get("val_loss", float("inf"))

    print("[MetaFSM] Propose (Qwen heavy)")
    agent_tracker.set_all_idle_except(
        focus_root, "propose", "Qwen heavy — اقتراح patch للكود", cycle
    )
    _update_job_phase(focus_root, cycle, "propose", "Meta Propose")
    proposal = run_meta_propose(store, task_md, cycle=cycle)
    if proposal.get("status") == "error":
        agent_tracker.set_agent(focus_root, "propose", "error", proposal.get("reason", "")[:120], cycle=cycle)
        return {"outcome": "ERROR", "reason": proposal.get("reason")}
    agent_tracker.set_agent(focus_root, "propose", "done", "اقتراح patch جاهز", cycle=cycle)

    print("[MetaFSM] PeerReview (Qwen heavy)")
    agent_tracker.set_all_idle_except(
        focus_root, "peer_review", "Qwen heavy — مراجعة patch", cycle
    )
    _update_job_phase(focus_root, cycle, "peer_review", "Meta PeerReview")
    review = run_meta_peer_review(store, task_md, proposal)
    if not review.get("approved") and proposal.get("source") == "research_queue":
        review = {"approved": True, "reasons": ["auto-approve research queue when Ollama offline"]}
    if not review.get("approved"):
        agent_tracker.set_agent(
            focus_root, "peer_review", "done", "مرفوض", cycle=cycle
        )
        _log_experiment(
            focus_root,
            {
                "cycle": cycle,
                "outcome": "DISCARD",
                "val_loss": champ_before,
                "reason": review.get("reasons"),
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        return {"outcome": "DISCARD", "approved": False}
    agent_tracker.set_agent(focus_root, "peer_review", "done", "موافق", cycle=cycle)

    unload_model_from_vram()

    print("[MetaFSM] Apply patches")
    agent_tracker.set_all_idle_except(
        focus_root, "execute", "تطبيق patch + benchmark", cycle
    )
    _update_job_phase(focus_root, cycle, "execute", "Meta Apply+Benchmark")
    patch_result = apply_changes(proposal.get("changes", []))
    if not patch_result.get("ok"):
        return {"outcome": "ERROR", "reason": patch_result.get("errors")}

    print("[MetaFSM] Benchmark")
    try:
        result = _run_benchmark(focus_root)
    except Exception as e:
        agent_tracker.set_agent(focus_root, "execute", "error", str(e)[:120], cycle=cycle)
        return {"outcome": "ERROR", "reason": str(e)}

    agent_tracker.set_agent(
        focus_root, "execute", "done", f"score={result.get('resource_score')}", cycle=cycle
    )

    score = float(result["resource_score"])
    champ = promotion.load_champion_json(focus_root)
    improved = score < champ.get("val_loss", float("inf"))
    outcome = "KEEP" if improved else "DISCARD"

    if not improved:
        from local.orchestrator.meta_patch import revert_last_backup

        revert_last_backup()

    promotion.promote_if_improved(focus_root, score, proposal.get("changes", [{}])[0])
    ingest_mod.ingest_experiment(
        store,
        proposal,
        {"val_loss": score, "outcome": outcome, "exp_id": result.get("exp_id", "meta")},
    )

    _log_experiment(
        focus_root,
        {
            "cycle": cycle,
            "exp_id": result.get("exp_id"),
            "val_loss": score,
            "outcome": outcome,
            "params": proposal.get("changes"),
            "metrics": result.get("metrics"),
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
    agent_tracker.set_all_idle_except(
        focus_root, "ingest", "تسجيل نتيجة meta", cycle
    )
    agent_tracker.set_agent(focus_root, "ingest", "done", f"outcome={outcome}", cycle=cycle)
    agent_tracker.mark_cycle_done(focus_root, cycle, f"{outcome} score={score:.2f}")
    return {"outcome": outcome, "resource_score": score, "metrics": result.get("metrics")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Meta FSM for experiments repo.")
    parser.add_argument("--focus-root", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=0, help="0 = unlimited")
    parser.add_argument("--cycle-start", type=int, default=1)
    parser.add_argument("--target-score", type=float, default=50.0)
    parser.add_argument("--pause", type=float, default=5.0)
    args = parser.parse_args()

    if not os.environ.get("AUTOSCIENTISTS_TARGET_REPO"):
        print("Set AUTOSCIENTISTS_TARGET_REPO to experiments clone", file=sys.stderr)
        sys.exit(1)

    cycle = args.cycle_start
    ran = 0
    from local.dashboard.job_status import read_job_status, write_job_status

    st0.update({"state": "running", "track": "meta", "dual_track": True, "pid": os.getpid()})
    write_job_status(args.focus_root, st0)
    agent_tracker.init_team(args.focus_root, cycle=cycle)

    while True:
        if args.max_cycles and ran >= args.max_cycles:
            break
        print(f"\n{'=' * 60}\nMETA CYCLE {cycle}\n{'=' * 60}")
        st = read_job_status(args.focus_root)
        st["current_cycle"] = cycle
        st["state"] = "running"
        write_job_status(args.focus_root, st)
        out = run_meta_iteration(args.focus_root, cycle=cycle)
        score = out.get("resource_score")
        if score is not None and score <= args.target_score:
            print(f"[MetaFSM] target score reached: {score}")
            break
        if args.max_cycles == 0 and out.get("outcome") == "ERROR":
            print("[MetaFSM] error — pausing 60s")
            time.sleep(60)
        cycle += 1
        ran += 1
        time.sleep(args.pause)

    stf = read_job_status(args.focus_root)
    stf.update({"state": "complete", "track": "meta", "current_cycle": cycle - 1})
    write_job_status(args.focus_root, stf)


if __name__ == "__main__":
    main()
