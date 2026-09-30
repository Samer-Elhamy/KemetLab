"""Job status helpers (isolated module — avoids executor import shadowing)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Do not mark running jobs stale while PID is not written yet (subprocess startup).
_PID_GRACE_SECONDS = 25


def _status_path(run_dir: Path) -> Path:
    return Path(run_dir).resolve() / "logs" / "job_status.json"


def read_job_status(run_dir: Path) -> dict:
    path = _status_path(run_dir)
    if not path.exists():
        return {"state": "idle"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"state": "unknown"}


def write_job_status(run_dir: Path, data: dict) -> None:
    path = _status_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(0x100000, False, pid)
            if not handle:
                return False
            kernel.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def peek_job_running(run_dir: Path) -> bool:
    """Check if worker is active — does NOT mutate job_status (safe for UI refresh)."""
    st = read_job_status(run_dir)
    if st.get("state") != "running":
        return False
    return _pid_alive(st.get("pid"))


def job_state_label(state: str | None) -> str:
    labels = {
        "idle": "في الانتظار",
        "running": "🟢 تعمل الآن",
        "complete": "✅ اكتملت كل الدورات",
        "stopped": "⏹️ متوقفة (لم تكتمل)",
        "stale": "⚠️ توقفت بشكل غير متوقع",
        "error": "❌ خطأ",
    }
    return labels.get(state or "idle", state or "?")


def _job_start_grace_active(st: dict) -> bool:
    """True if job recently started and PID may not be assigned yet."""
    if st.get("pid"):
        return False
    raw = st.get("started_at")
    if not raw:
        return False
    try:
        t0 = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - t0).total_seconds()
        return 0 <= age < _PID_GRACE_SECONDS
    except (ValueError, TypeError):
        return False


def repair_stale_job(run_dir: Path) -> bool:
    run_dir = Path(run_dir).resolve()
    st = read_job_status(run_dir)
    if st.get("state") != "running":
        return False
    if _pid_alive(st.get("pid")):
        return False
    if _job_start_grace_active(st):
        return False
    stop_file = run_dir / "logs" / "STOP"
    new_state = "stopped" if stop_file.exists() else "stale"
    msg = (
        "أوقفت المهمة يدوياً — يمكنك متابعة الدورات لاحقاً"
        if new_state == "stopped"
        else "انتهت العملية دون تحديث الحالة — يمكنك البدء من جديد"
    )
    write_job_status(
        run_dir,
        {
            **st,
            "state": new_state,
            "error": msg,
            "pid": None,
            "finished_at": st.get("finished_at"),
        },
    )
    return True


def is_job_running(run_dir: Path) -> bool:
    if peek_job_running(run_dir):
        return True
    repair_stale_job(run_dir)
    return False


def should_auto_refresh_agents(run_dir: Path) -> bool:
    """True while a job is running or status still says running (UI polling)."""
    job = read_job_status(run_dir)
    if job.get("state") == "running":
        return True
    return peek_job_running(run_dir)
