"""Saved missions (runs) — list, resume, preserve champion/graph data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local.dashboard.data import load_champion, read_jsonl, run_metadata
from local.dashboard.job_status import read_job_status


def _meta_path(run_dir: Path) -> Path:
    return Path(run_dir).resolve() / "logs" / "mission_meta.json"


def load_mission_meta(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    path = _meta_path(run_dir)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    goal = ""
    ug = run_dir / "logs" / "user_goal.txt"
    if ug.exists():
        goal = ug.read_text(encoding="utf-8").strip()
    return {
        "title": run_dir.name,
        "goal": goal,
        "created_at": datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc).isoformat(),
        "task_bundle": "task-smoke-local",
    }


def save_mission_meta(
    run_dir: Path,
    *,
    title: str,
    goal: str,
    task_bundle: str = "task-smoke-local",
    touch_started: bool = False,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    existing = load_mission_meta(run_dir) if _meta_path(run_dir).exists() else {}
    meta = {
        **existing,
        "title": (title or run_dir.name).strip(),
        "goal": goal.strip(),
        "task_bundle": task_bundle,
        "path": str(run_dir),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if "created_at" not in meta:
        meta["created_at"] = meta["updated_at"]
    if touch_started:
        meta["last_started_at"] = meta["updated_at"]
    _meta_path(run_dir).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def is_mission_dir(path: Path) -> bool:
    path = Path(path)
    if not path.is_dir():
        return False
    markers = (
        path / "RUNTIME",
        path / "champion.json",
        path / "logs" / "mission_meta.json",
        path / "logs" / "experiments.jsonl",
        path / "logs" / "baseline.json",
    )
    return any(m.exists() for m in markers)


def discover_missions(template_dir: Path | None = None) -> list[Path]:
    template_dir = template_dir or Path(__file__).resolve().parents[2]
    parent = template_dir.parent
    roots = [parent, Path.home(), template_dir]
    found: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for child in root.iterdir():
                if child.is_dir() and is_mission_dir(child):
                    found[str(child.resolve())] = child.resolve()
        except PermissionError:
            continue
    return sorted(found.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def next_cycle_number(run_dir: Path) -> int:
    rows = read_jsonl(Path(run_dir).resolve() / "logs" / "experiments.jsonl")
    if not rows:
        return 1
    return max(int(r.get("cycle", 0)) for r in rows) + 1


def mission_summary(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    meta = load_mission_meta(run_dir)
    champ = load_champion(run_dir)
    job = read_job_status(run_dir)
    n_cycles = len(
        {int(r["cycle"]) for r in read_jsonl(run_dir / "logs" / "experiments.jsonl") if "cycle" in r}
    )
    n_exps = len(read_jsonl(run_dir / "logs" / "experiments.jsonl"))
    return {
        "path": str(run_dir),
        "folder": run_dir.name,
        "title": meta.get("title", run_dir.name),
        "goal": (meta.get("goal") or "")[:120],
        "champion_val_loss": champ.get("val_loss"),
        "cycles_done": n_cycles,
        "experiments": n_exps,
        "job_state": job.get("state", "idle"),
        "next_cycle": next_cycle_number(run_dir),
        "task_type": run_metadata(run_dir).get("task_type", "?"),
    }


def list_mission_summaries(template_dir: Path | None = None) -> list[dict[str, Any]]:
    return [mission_summary(p) for p in discover_missions(template_dir)]


def prepare_mission_for_run(run_dir: Path) -> dict[str, Any]:
    """Clear stop flags, repair stale jobs, allow resume on completed missions."""
    from local.orchestrator.agent_tracker import clear_stop

    from local.dashboard.job_status import is_job_running, repair_stale_job, write_job_status

    run_dir = Path(run_dir).resolve()
    clear_stop(run_dir)
    repair_stale_job(run_dir)

    if is_job_running(run_dir):
        job = read_job_status(run_dir)
        return {
            "ok": False,
            "error": "المهمة تعمل الآن — انتظر أو اضغط إيقاف/إصلاح حالة عالقة.",
            "job": job,
        }

    job = read_job_status(run_dir)
    # Allow new batch after complete / stopped / stale / error — only block if truly running
    if job.get("state") in ("running", "stale"):
        from local.dashboard.job_status import peek_job_running

        if not peek_job_running(run_dir):
            write_job_status(
                run_dir,
                {
                    **job,
                    "state": "idle",
                    "pid": None,
                    "note": "reset for new run batch",
                },
            )

    nxt = next_cycle_number(run_dir)
    return {"ok": True, "next_cycle": nxt, "resume": nxt > 1}
