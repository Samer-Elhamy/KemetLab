"""Live agent status for long-running dashboard jobs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local.orchestrator.agent_registry import LOCAL_AGENTS

STOP_FILE = "STOP"
LIVE_FILE = "agents_live.json"
EVENTS_FILE = "agents_events.jsonl"


def _live_path(focus_root: Path) -> Path:
    return focus_root / "logs" / LIVE_FILE


def _events_path(focus_root: Path) -> Path:
    return focus_root / "logs" / EVENTS_FILE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_stop_requested(focus_root: Path) -> bool:
    return (focus_root / "logs" / STOP_FILE).exists()


def request_stop(focus_root: Path) -> None:
    path = focus_root / "logs" / STOP_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_now(), encoding="utf-8")


def clear_stop(focus_root: Path) -> None:
    path = focus_root / "logs" / STOP_FILE
    if path.exists():
        path.unlink()


def init_team(focus_root: Path, cycle: int = 0) -> None:
    """Reset all agents to idle at job or cycle boundary."""
    agents = []
    for spec in LOCAL_AGENTS:
        agents.append(
            {
                **spec,
                "status": "idle",
                "detail": "في الانتظار",
                "cycle": cycle,
                "updated_at": _now(),
            }
        )
    write_live(
        focus_root,
        {
            "cycle": cycle,
            "job_state": "running",
            "updated_at": _now(),
            "agents": agents,
            "active_count": 0,
            "total_agents": len(agents),
        },
    )


def write_live(focus_root: Path, payload: dict[str, Any]) -> None:
    path = _live_path(focus_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    agents = payload.get("agents") or []
    working = sum(1 for a in agents if a.get("status") == "working")
    payload["active_count"] = working
    payload["total_agents"] = len(agents)
    payload["updated_at"] = _now()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_live(focus_root: Path) -> dict[str, Any]:
    path = _live_path(focus_root)
    if not path.exists():
        return {
            "agents": [],
            "active_count": 0,
            "total_agents": len(LOCAL_AGENTS),
            "job_state": "idle",
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"agents": [], "active_count": 0, "job_state": "unknown"}


def _log_event(focus_root: Path, event: dict[str, Any]) -> None:
    path = _events_path(focus_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**event, "ts": _now()}, ensure_ascii=False) + "\n")


def set_agent(
    focus_root: Path,
    agent_id: str,
    status: str,
    detail: str = "",
    *,
    cycle: int | None = None,
) -> None:
    """status: idle | working | done | error | skipped"""
    live = read_live(focus_root)
    agents = live.get("agents") or []
    if not agents:
        init_team(focus_root, cycle or 0)
        live = read_live(focus_root)
        agents = live["agents"]

    found = False
    for a in agents:
        if a.get("id") == agent_id:
            if a.get("status") != status or a.get("detail") != detail:
                _log_event(
                    focus_root,
                    {
                        "agent_id": agent_id,
                        "status": status,
                        "detail": detail,
                        "cycle": cycle if cycle is not None else live.get("cycle"),
                    },
                )
            a["status"] = status
            a["detail"] = detail or a.get("detail", "")
            if cycle is not None:
                a["cycle"] = cycle
            a["updated_at"] = _now()
            found = True
            break

    if not found:
        spec = next((x for x in LOCAL_AGENTS if x["id"] == agent_id), {"id": agent_id})
        agents.append(
            {
                **spec,
                "status": status,
                "detail": detail,
                "cycle": cycle or live.get("cycle", 0),
                "updated_at": _now(),
            }
        )

    if cycle is not None:
        live["cycle"] = cycle
    live["agents"] = agents
    write_live(focus_root, live)


def set_all_idle_except(focus_root: Path, working_id: str | None, detail: str, cycle: int) -> None:
    """Legacy single-worker API — prefer set_workers for multi-agent teams."""
    if working_id:
        set_workers(focus_root, [(working_id, detail)], cycle=cycle)
    else:
        set_workers(focus_root, [], cycle=cycle)


def set_workers(
    focus_root: Path,
    workers: list[tuple[str, str]],
    *,
    cycle: int,
    orchestrator_detail: str | None = None,
) -> None:
    """Mark multiple agents working at once (teams / parallel analysts)."""
    live = read_live(focus_root)
    agents = list(live.get("agents") or [])
    if not agents:
        init_team(focus_root, cycle)
        live = read_live(focus_root)
        agents = list(live.get("agents"))

    work_map = {wid: det for wid, det in workers}
    worker_ids = set(work_map.keys())
    orch_detail = orchestrator_detail or (
        f"دورة {cycle} — {len(worker_ids)} وكيل نشط" if worker_ids else f"دورة {cycle}"
    )

    updated = []
    for a in agents:
        aid = a.get("id", "")
        prev_status = a.get("status")
        prev_detail = a.get("detail")
        if aid in work_map:
            status, det = "working", work_map[aid]
        elif aid == "orchestrator" and worker_ids:
            status, det = "working", orch_detail
        elif prev_status in ("done", "error", "skipped") and aid not in worker_ids:
            status, det = prev_status, prev_detail
        else:
            status, det = "idle", "في الانتظار"
        if prev_status != status or prev_detail != det:
            _log_event(
                focus_root,
                {"agent_id": aid, "status": status, "detail": det, "cycle": cycle},
            )
        updated.append({**a, "status": status, "detail": det, "cycle": cycle, "updated_at": _now()})

    live["agents"] = updated
    live["cycle"] = cycle
    live["job_state"] = "running"
    live["mode"] = live.get("mode") or "teams"
    live["current_workers"] = list(worker_ids)
    live["current_worker"] = next(iter(worker_ids), None)
    write_live(focus_root, live)


def bootstrap_job_start(
    focus_root: Path,
    cycle: int,
    message: str = "تشغيل العملية...",
    *,
    teams: list[dict] | None = None,
) -> None:
    """Visible immediately when user clicks Start (before subprocess warms up)."""
    from local.orchestrator.team_manager import build_team_agent_specs, load_or_seed_roster

    if teams is None:
        teams = load_or_seed_roster(focus_root)
    agents = []
    for spec in LOCAL_AGENTS:
        if spec["id"] == "orchestrator":
            agents.append(
                {
                    **spec,
                    "status": "working",
                    "detail": message,
                    "cycle": cycle,
                    "updated_at": _now(),
                }
            )
        else:
            agents.append(
                {
                    **spec,
                    "status": "idle",
                    "detail": "بانتظار دوره في الطابور",
                    "cycle": cycle,
                    "updated_at": _now(),
                }
            )
    for spec in build_team_agent_specs(teams):
        agents.append(
            {
                **spec,
                "status": "idle",
                "detail": "بانتظار تشكيل الفريق",
                "cycle": cycle,
                "updated_at": _now(),
            }
        )
    write_live(
        focus_root,
        {
            "cycle": cycle,
            "job_state": "running",
            "mode": "teams",
            "team_count": len(teams),
            "current_worker": "orchestrator",
            "current_workers": ["orchestrator"],
            "agents": agents,
        },
    )


def mark_cycle_done(focus_root: Path, cycle: int, summary: str) -> None:
    """End of one FSM cycle — keep orchestrator visible; others wait (not all «done»)."""
    prev = read_live(focus_root)
    prev_agents = prev.get("agents") or []
    agents = []
    seen = set()
    for a in prev_agents:
        aid = a.get("id", "")
        seen.add(aid)
        if aid == "orchestrator":
            status, detail = "working", summary[:200]
        else:
            status, detail = "idle", "اكتملت الدورة — في الانتظار"
        agents.append({**a, "status": status, "detail": detail, "cycle": cycle, "updated_at": _now()})
    for spec in LOCAL_AGENTS:
        if spec["id"] not in seen:
            aid = spec["id"]
            status, detail = (
                ("working", summary[:200]) if aid == "orchestrator" else ("idle", "اكتملت الدورة — في الانتظار")
            )
            agents.append(
                {**spec, "status": status, "detail": detail, "cycle": cycle, "updated_at": _now()}
            )
    write_live(
        focus_root,
        {
            **{k: prev[k] for k in ("mode", "team_count") if k in prev},
            "cycle": cycle,
            "job_state": "between_cycles",
            "current_worker": "orchestrator",
            "current_workers": ["orchestrator"],
            "agents": agents,
        },
    )


def read_recent_events(focus_root: Path, limit: int = 30) -> list[dict[str, Any]]:
    path = _events_path(focus_root)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-limit:]:
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows
