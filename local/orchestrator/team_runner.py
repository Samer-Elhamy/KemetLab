"""Multi-team cycle: parallel analysts, serial GPU, flexible team reform."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local.memory import GraphStore
from local.memory import blocks as block_mod
from local.memory import ingest as ingest_mod
from local.memory import shard_commit
from local.orchestrator import agent_tracker, critical_path, fsm, promotion, shards
from local.orchestrator.runner import _log_experiment, _log_session, _run_train, _update_job_phase
from local.orchestrator.team_manager import (
    build_team_agent_specs,
    load_or_seed_roster,
    reform_teams,
    should_reform_teams,
    team_agent_id,
)

# Serialize LLM + train on one GPU
_resource_lock = threading.Lock()


def _team_mode_enabled() -> bool:
    return os.environ.get("LOCAL_TEAM_MODE", "1").lower() not in ("0", "false", "no")


def _sync_live_agents(focus_root: Path, teams: list[dict[str, Any]], cycle: int) -> None:
    from local.orchestrator.agent_registry import LOCAL_AGENTS

    agents = []
    for spec in LOCAL_AGENTS:
        agents.append(
            {
                **spec,
                "status": "idle",
                "detail": "في الانتظار",
                "cycle": cycle,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    for spec in build_team_agent_specs(teams):
        agents.append(
            {
                **spec,
                "status": "idle",
                "detail": "في الانتظار",
                "cycle": cycle,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    agent_tracker.write_live(
        focus_root,
        {
            "cycle": cycle,
            "job_state": "running",
            "mode": "teams",
            "team_count": len(teams),
            "agents": agents,
        },
    )


def _run_team_propose_review(
    focus_root: Path,
    store: GraphStore,
    task_md: str,
    team: dict[str, Any],
    cycle: int,
) -> dict[str, Any]:
    """One team: analyst propose + reviewer (LLM under global lock)."""
    tid = team["id"]
    aid = team_agent_id(tid, "analyst")
    rid = team_agent_id(tid, "reviewer")
    hyp = team.get("hypothesis", "")

    agent_tracker.set_workers(
        focus_root,
        [
            (aid, f"اقتراح — {hyp[:50]}"),
            (rid, "بانتظار اقتراح المحلل"),
        ],
        cycle=cycle,
    )
    _update_job_phase(focus_root, cycle, aid, f"Propose [{tid}]")

    task_slice = task_md + f"\n\n## فرق: {team.get('name_ar', tid)}\nفرضية: {hyp}\n"

    with _resource_lock:
        agent_tracker.set_workers(
            focus_root,
            [(aid, "qwen35custom — توليد اقتراح"), (rid, "مراجعة جاهزة")],
            cycle=cycle,
        )
        team_idx = int(tid.replace("team_", "")) if str(tid).startswith("team_") else 0
        proposal = fsm.run_propose(
            store,
            task_slice,
            focus_root=focus_root,
            cycle=cycle,
            team_offset=team_idx,
        )
        if proposal.get("status") == "error":
            agent_tracker.set_agent(
                focus_root, aid, "error", proposal.get("reason", "error")[:120], cycle=cycle
            )
            return {"team_id": tid, "ok": False, "reason": proposal.get("reason")}

        agent_tracker.set_agent(focus_root, aid, "done", "اقتراح جاهز", cycle=cycle)
        agent_tracker.set_workers(
            focus_root,
            [(rid, "مراجعة الاقتراح"), (aid, "انتهى — بانتظار المراجعة")],
            cycle=cycle,
        )
        review = fsm.run_peer_review(store, task_md, proposal)
        approved = bool(review.get("approved", False))

    if approved:
        agent_tracker.set_agent(
            focus_root, rid, "done", "موافق — في طابور GPU", cycle=cycle
        )
    else:
        agent_tracker.set_agent(
            focus_root,
            rid, "done", "مرفوض — " + "; ".join(review.get("reasons", [])[:1])[:100], cycle=cycle
        )
        agent_tracker.set_agent(focus_root, team_agent_id(tid, "gpu"), "skipped", "لم تُوافق", cycle=cycle)

    return {
        "team_id": tid,
        "ok": True,
        "approved": approved,
        "proposal": proposal,
        "review": review,
    }


def run_team_iteration(focus_root: Path, cycle: int = 1) -> dict:
    focus_root = Path(focus_root).resolve()
    task_md = (focus_root / "task" / "TASK.md").read_text(encoding="utf-8")
    store = GraphStore(focus_root)
    try:
        return _run_team_iteration_inner(focus_root, store, task_md, cycle)
    finally:
        store.close()


def _run_team_iteration_inner(
    focus_root: Path,
    store: GraphStore,
    task_md: str,
    cycle: int,
) -> dict:
    teams = load_or_seed_roster(focus_root)
    _sync_live_agents(focus_root, teams, cycle)

    agent_tracker.set_workers(
        focus_root,
        [("orchestrator", f"دورة {cycle} — وضع الفرق"), ("shard_cpu", "تحليل Graph-RAG")],
        cycle=cycle,
    )
    _update_job_phase(focus_root, cycle, "orchestrator", "تنسيق الفرق")

    block = block_mod.open_block()
    champ_before = promotion.load_champion_json(focus_root).get("val_loss", float("inf"))

    shard_propose = shards.create_shard("propose", task_md[:2000])
    cp = critical_path.decompose_and_run(
        [
            ("verify_graph", lambda: store.nodes_by_kind("Champion", limit=1)),
            ("shard_propose_buf", lambda: shard_propose.append("teams loaded")),
        ]
    )

    do_reform, reason = should_reform_teams(focus_root, cycle)
    if do_reform:
        analyst_ids = [team_agent_id(t["id"], "analyst") for t in teams]
        agent_tracker.set_workers(
            focus_root,
            [("orchestrator", f"مناقشة وتشكيل — {reason}")]
            + [(aid, "مناقشة فرضية الفريق") for aid in analyst_ids],
            cycle=cycle,
        )
        _update_job_phase(focus_root, cycle, "orchestrator", f"Discuss/Reform: {reason}")
        teams = reform_teams(focus_root, cycle, reason)
        _sync_live_agents(focus_root, teams, cycle)
        agent_tracker.set_workers(
            focus_root,
            [(team_agent_id(t["id"], "analyst"), "فرق جديدة — جاهز") for t in teams],
            cycle=cycle,
        )

    # Parallel team propose+review (LLM serialized inside lock; UI shows all teams active)
    print(f"[FSM] teams={len(teams)} parallel propose")
    analyst_work = [(team_agent_id(t["id"], "analyst"), f"اقتراح متوازي — {t['id']}") for t in teams]
    agent_tracker.set_workers(
        focus_root,
        [("orchestrator", "مراقبة الفرق المتوازية")] + analyst_work,
        cycle=cycle,
    )

    results: list[dict[str, Any]] = []
    max_workers = min(len(teams), int(os.environ.get("LOCAL_TEAM_THREADS", "3")))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(_run_team_propose_review, focus_root, store, task_md, team, cycle): team
            for team in teams
        }
        for fut in as_completed(futs):
            if agent_tracker.is_stop_requested(focus_root):
                break
            results.append(fut.result())

    approved_runs = [r for r in results if r.get("ok") and r.get("approved")]
    print(f"[FSM] approved teams={len(approved_runs)}/{len(teams)}")

    # Serial GPU queue — multiple GPUs shown working (active + queued)
    best: dict[str, Any] | None = None
    for i, run in enumerate(approved_runs):
        tid = run["team_id"]
        gid = team_agent_id(tid, "gpu")
        queued = [team_agent_id(r["team_id"], "gpu") for r in approved_runs[i + 1 :]]
        workers = [(gid, "train.py — تدريب تجربة الفريق")]
        for qid in queued:
            workers.append((qid, "في طابور GPU — انتظار"))
        if i == 0:
            workers.append(("execute", "دعم تنفيذ مشترك"))
        agent_tracker.set_workers(focus_root, workers, cycle=cycle)
        _update_job_phase(focus_root, cycle, gid, f"Execute [{tid}]")

        proposal = run["proposal"]
        with _resource_lock:
            train_result = _run_train(focus_root, proposal.get("params", {}))
        val_loss = float(train_result["val_loss"])
        agent_tracker.set_agent(
            focus_root, gid, "done", f"val_loss={val_loss:.6f}", cycle=cycle
        )

        champ = promotion.load_champion_json(focus_root)
        improved = val_loss < champ.get("val_loss", float("inf"))
        outcome = "KEEP" if improved else "DISCARD"
        if best is None or val_loss < best.get("val_loss", float("inf")):
            best = {
                "team_id": tid,
                "val_loss": val_loss,
                "outcome": outcome,
                "proposal": proposal,
                "result": train_result,
            }

    if not best:
        agent_tracker.mark_cycle_done(focus_root, cycle, "لا اقتراحات مقبولة — دورة فرق")
        block_mod.close_block(
            store,
            block,
            {"outcome": "DISCARD", "key_findings": ["no approved team proposals"]},
            champ_before,
            champ_before,
        )
        return {"state": "done", "outcome": "DISCARD", "teams": len(teams)}

    val_loss = best["val_loss"]
    outcome = best["outcome"]
    proposal = best["proposal"]

    agent_tracker.set_workers(
        focus_root,
        [("ingest", "تسجيل نتائج الفرق"), ("graph", "تحديث Graph-RAG")],
        cycle=cycle,
    )
    _update_job_phase(focus_root, cycle, "ingest", "Ingest teams")

    exp_id = ingest_mod.ingest_experiment(
        store,
        proposal,
        {
            "val_loss": val_loss,
            "outcome": outcome,
            "exp_id": best["result"].get("exp_id", f"team-{cycle}"),
            "team_id": best["team_id"],
        },
    )
    ingest_mod.ensure_champion(store, val_loss, proposal.get("params", {}))
    promotion.promote_if_improved(
        focus_root,
        val_loss,
        proposal.get("params", {}),
        focus_root / "task" / "repo" / "train.py",
    )
    champ_after = promotion.load_champion_json(focus_root).get("val_loss", val_loss)

    agent_tracker.set_agent(focus_root, "ingest", "done", f"فريق {best['team_id']}", cycle=cycle)
    agent_tracker.set_agent(focus_root, "graph", "done", f"champion={champ_after}", cycle=cycle)

    _log_experiment(
        focus_root,
        {
            "cycle": cycle,
            "exp_id": exp_id,
            "val_loss": val_loss,
            "outcome": outcome,
            "team_id": best["team_id"],
            "teams_active": len(teams),
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
    _log_session(
        focus_root,
        {
            "cycle": cycle,
            "phase": "team_cycle_complete",
            "serial_collapse": cp.serial_collapse,
            "teams": [t["id"] for t in teams],
            "winner": best["team_id"],
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
    block_mod.close_block(
        store,
        block,
        {
            "outcome": outcome,
            "key_findings": [f"team={best['team_id']}", f"val_loss={val_loss}"],
        },
        champ_before,
        champ_after,
    )
    agent_tracker.mark_cycle_done(
        focus_root, cycle, f"فرق — {outcome} فريق {best['team_id']} loss={val_loss:.6f}"
    )
    return {
        "state": "done",
        "outcome": outcome,
        "val_loss": val_loss,
        "team_id": best["team_id"],
        "teams": len(teams),
    }
