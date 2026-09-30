"""Create local runs and execute the FSM from the dashboard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from local.dashboard.repo_root import find_repo_root

_REPO = find_repo_root(Path(__file__))

USER_GOAL_MARKER = "## هدف البحث (من لوحة التحكم)"


from local.dashboard.job_status import (  # noqa: E402
    is_job_running,
    read_job_status,
    repair_stale_job,
    write_job_status,
)

# Back-compat for run_job.py
_write_status = write_job_status


def _resolve_python(template_dir: Path) -> str:
    """Prefer kaggle .venv containing full ML suite (lightgbm, xgboost, scikit-learn, polars)."""
    kaggle_py = Path("C:/Users/Samer/kaggle/.venv/Scripts/python.exe")
    if kaggle_py.exists():
        return str(kaggle_py)
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = template_dir / rel.replace("/", os.sep)
        if candidate.exists():
            return str(candidate)
    return sys.executable


def patch_user_goal(run_dir: Path, goal: str) -> None:
    goal = goal.strip()
    if not goal:
        return
    task_md = run_dir / "task" / "TASK.md"
    if not task_md.exists():
        task_md.parent.mkdir(parents=True, exist_ok=True)
        task_md.write_text(
            "---\ntask_type: optimization\nmetric: val_loss\ndirection: minimize\n---\n\n",
            encoding="utf-8",
        )
    text = task_md.read_text(encoding="utf-8")
    block = f"{USER_GOAL_MARKER}\n\n{goal}\n"
    if USER_GOAL_MARKER in text:
        head, _, _tail = text.partition(USER_GOAL_MARKER)
        text = head.rstrip() + "\n\n" + block
    else:
        text = text.rstrip() + "\n\n" + block
    task_md.write_text(text, encoding="utf-8")
    (run_dir / "logs" / "user_goal.txt").write_text(goal, encoding="utf-8")


def _safe_folder_name(title: str | None, ts: str) -> str:
    if title and title.strip():
        base = "".join(c if c.isalnum() or c in "-_" else "_" for c in title.strip())[:48]
        base = base.strip("_") or "mission"
        return f"{base}_{ts}"
    return f"dashboard_{ts}"


def create_dashboard_run(
    goal: str,
    *,
    title: str | None = None,
    template_dir: Path | None = None,
    task_bundle: str = "task-smoke-local",
    parent_dir: Path | None = None,
) -> Path:
    template_dir = (template_dir or _REPO).resolve()
    task_path = Path(task_bundle)
    if not task_path.is_absolute():
        task_path = (template_dir / task_bundle).resolve()
    if not (task_path / "TASK.md").exists():
        raise FileNotFoundError(f"Task not found: {task_path}")

    import yaml

    from local.launch_local import bootstrap_local_run

    ts = datetime.now(timezone.utc).strftime("%m%d_%H%M%S")
    parent = (parent_dir or template_dir.parent).resolve()
    run_dir = parent / _safe_folder_name(title, ts)
    if run_dir.exists():
        raise FileExistsError(run_dir)

    raw = (task_path / "TASK.md").read_text(encoding="utf-8")
    parts = raw.split("---")
    task_type = "optimization"
    if len(parts) >= 3:
        fm = yaml.safe_load(parts[1]) or {}
        task_type = fm.get("task_type", "optimization")

    bootstrap_local_run(template_dir, run_dir, task_path, task_type)
    patch_user_goal(run_dir, goal)
    from local.dashboard.missions import save_mission_meta

    save_mission_meta(
        run_dir,
        title=(title or run_dir.name).strip(),
        goal=goal,
        task_bundle=task_bundle,
    )
    return run_dir


def create_mission_only(
    goal: str,
    *,
    title: str | None = None,
    template_dir: Path | None = None,
    task_bundle: str = "task-smoke-local",
) -> Path:
    """Create a new mission folder without starting FSM (data preserved for later)."""
    return create_dashboard_run(
        goal,
        title=title,
        template_dir=template_dir,
        task_bundle=task_bundle,
    )


def request_stop_job(run_dir: Path) -> None:
    from local.orchestrator.agent_tracker import request_stop

    request_stop(Path(run_dir).resolve())


def start_runner_job(
    run_dir: Path,
    *,
    cycles: int = 1,
    max_hours: float = 0,
    pause_seconds: float = 2.0,
    goal: str | None = None,
    template_dir: Path | None = None,
    update_goal: bool = True,
) -> dict:
    from local.dashboard.missions import prepare_mission_for_run, save_mission_meta

    run_dir = Path(run_dir).resolve()
    prep = prepare_mission_for_run(run_dir)
    if not prep.get("ok"):
        return {
            "ok": False,
            "error": prep.get("error", "لا يمكن البدء"),
            "status": prep.get("job") or read_job_status(run_dir),
        }

    cycle_start = int(prep.get("next_cycle", 1))

    if goal and update_goal:
        patch_user_goal(run_dir, goal)
        meta = save_mission_meta(
            run_dir,
            title=load_mission_title(run_dir),
            goal=goal,
            touch_started=True,
        )
    else:
        from local.dashboard.missions import load_mission_meta

        meta = load_mission_meta(run_dir)
        save_mission_meta(
            run_dir,
            title=meta.get("title", run_dir.name),
            goal=meta.get("goal", ""),
            touch_started=True,
        )

    max_hours = float(max_hours or 0)
    pause_seconds = float(pause_seconds if pause_seconds is not None else 2.0)
    cycles = int(cycles)
    if cycles < 0:
        cycles = 0
    if cycles == 0 and max_hours <= 0:
        cycles = 1  # safety default

    template_dir = (template_dir or _REPO).resolve()
    log_path = run_dir / "logs" / "runner.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat()
    status: dict = {
        "state": "running",
        "cycles_total": cycles if cycles > 0 else None,
        "cycles_done": 0,
        "cycle_start": cycle_start,
        "resume": cycle_start > 1,
        "max_hours": max_hours if max_hours > 0 else None,
        "pause_seconds": pause_seconds,
        "started_at": started,
        "goal": (goal or "").strip() if goal else None,
        "log": str(log_path),
        "long_run": max_hours > 0 or cycles == 0,
    }
    if max_hours > 0:
        from datetime import timedelta

        status["ends_at"] = (datetime.now(timezone.utc) + timedelta(hours=max_hours)).isoformat()
    _write_status(run_dir, status)

    from local.dashboard.sync_runtime import sync_runtime_from_repo
    from local.llm.runtime_health import mock_mode_enabled, run_runtime_health, save_health_report
    from local.orchestrator import agent_tracker
    from local.orchestrator.team_manager import load_or_seed_roster

    template_dir = (template_dir or _REPO).resolve()
    sync_runtime_from_repo(run_dir, template_dir)

    if not hasattr(agent_tracker, "bootstrap_job_start"):
        import importlib

        agent_tracker = importlib.reload(agent_tracker)
    if not hasattr(agent_tracker, "bootstrap_job_start"):
        return {
            "ok": False,
            "error": (
                "نسخة قديمة من agent_tracker — شغّل اللوحة من "
                f"`{template_dir}` وليس من مجلد مهمة قديم."
            ),
        }

    health = run_runtime_health(quick_probe=mock_mode_enabled())
    save_health_report(run_dir, health)
    if not health.get("ready_for_real_run") and not mock_mode_enabled():
        miss = health.get("missing_models") or []
        err = health.get("summary_ar", "Ollama غير جاهز")
        if miss:
            err += "\n\n```\nollama pull " + "\nollama pull ".join(miss) + "\n```"
        return {
            "ok": False,
            "error": err,
            "runtime_health": health,
        }

    teams = load_or_seed_roster(run_dir)
    agent_tracker.bootstrap_job_start(
        run_dir,
        cycle_start,
        f"جاري تشغيل {len(teams)} فرق متوازية...",
        teams=teams,
    )
    st = read_job_status(run_dir)
    st["current_phase"] = "انتظار العملية الخلفية"
    st["current_agent"] = "orchestrator"
    write_job_status(run_dir, st)

    python = _resolve_python(template_dir)
    job_script = template_dir / "local" / "dashboard" / "run_job.py"

    with open(log_path, "a", encoding="utf-8") as log_f:
        log_f.write(
            f"\n--- job start {started} python={python} "
            f"cycles={cycles} cycle_start={cycle_start} max_hours={max_hours} "
            f"pause={pause_seconds}s resume={cycle_start > 1} ---\n"
        )

    cmd = [
        python,
        str(job_script),
        "--focus-root",
        str(run_dir),
        "--max-cycles",
        str(cycles),
        "--cycle-start",
        str(cycle_start),
        "--pause-seconds",
        str(pause_seconds),
        "--log-file",
        str(log_path),
    ]
    if max_hours > 0:
        cmd.extend(["--max-hours", str(max_hours)])

    child_env = {
        **os.environ,
        "PYTHONPATH": str(template_dir)
        + os.pathsep
        + os.environ.get("PYTHONPATH", ""),
        "PYTHONUNBUFFERED": "1",
    }
    child_env.pop("LOCAL_MOCK_LLM", None)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(template_dir),
            env=child_env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError as exc:
        _write_status(
            run_dir,
            {**read_job_status(run_dir), "state": "error", "error": str(exc)},
        )
        return {"ok": False, "error": str(exc)}

    _write_status(
        run_dir,
        {
            **read_job_status(run_dir),
            "pid": proc.pid,
            "python": python,
        },
    )

    # Fail fast if the worker exits immediately (import error, bad python, etc.)
    import time

    time.sleep(0.6)
    if proc.poll() is not None:
        tail = ""
        if log_path.exists():
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-800:]
        _write_status(
            run_dir,
            {
                **read_job_status(run_dir),
                "state": "error",
                "error": f"العملية توقفت فوراً (exit={proc.returncode})",
                "pid": None,
            },
        )
        return {
            "ok": False,
            "error": f"فشل بدء التشغيل (كود {proc.returncode}). راجع السجل أدناه.",
            "log_tail": tail,
        }

    return {
        "ok": True,
        "pid": proc.pid,
        "run_dir": str(run_dir),
        "log": str(log_path),
        "cycle_start": cycle_start,
        "resume": cycle_start > 1,
    }


def load_mission_title(run_dir: Path) -> str:
    from local.dashboard.missions import load_mission_meta

    return load_mission_meta(run_dir).get("title", Path(run_dir).name)
