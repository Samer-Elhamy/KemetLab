#!/usr/bin/env python3
"""Run one FSM cycle via run_job and poll until done + monitor report."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
os.chdir(_REPO)

from local.dashboard.job_status import read_job_status, repair_stale_job, write_job_status
from local.dashboard.missions import prepare_mission_for_run
from local.dashboard.cycle_monitor import load_monitor_report, list_monitor_history
from local.llm.secrets import bootstrap_env

bootstrap_env()


def _python() -> str:
    v = _REPO / ".venv" / "Scripts" / "python.exe"
    return str(v) if v.exists() else sys.executable


def main() -> int:
    focus = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "dashboard_0602_174304"
    focus = focus.resolve()
    if not focus.is_dir():
        print(f"Missing run dir: {focus}", flush=True)
        return 1

    repair_stale_job(focus)
    prep = prepare_mission_for_run(focus)
    if not prep.get("ok"):
        print("Cannot start:", prep, flush=True)
        return 1

    cycle_start = int(prep["next_cycle"])
    log_path = focus / "logs" / "runner.log"

    cmd = [
        _python(),
        str(_REPO / "local" / "dashboard" / "run_job.py"),
        "--focus-root",
        str(focus),
        "--max-cycles",
        "1",
        "--cycle-start",
        str(cycle_start),
        "--pause-seconds",
        "0",
        "--log-file",
        str(log_path),
    ]
    env = {
        **os.environ,
        "PYTHONPATH": str(_REPO),
        "PYTHONUNBUFFERED": "1",
        "LOCAL_LLM_PROVIDER": os.environ.get("LOCAL_LLM_PROVIDER", "openrouter"),
        "LOCAL_TEAM_MODE": "0",
    }
    env.pop("LOCAL_MOCK_LLM", None)

    print(f"[WATCH] start cycle={cycle_start} root={focus}", flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(_REPO),
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    last_phase = ""
    while proc.poll() is None:
        st = read_job_status(focus)
        phase = st.get("current_phase", "")
        state = st.get("state", "running")
        agent = st.get("current_agent", "")
        if phase != last_phase:
            line = (
                f"[WATCH] state={state} phase={phase} agent={agent} "
                f"cycle={st.get('current_cycle')} done={st.get('cycles_done')}"
            )
            try:
                print(line, flush=True)
            except UnicodeEncodeError:
                print(line.encode("ascii", errors="replace").decode(), flush=True)
            last_phase = phase
        time.sleep(3)

    code = proc.wait()
    print(f"[WATCH] run_job exit={code}", flush=True)

    st = read_job_status(focus)
    print(f"[WATCH] final job state={st.get('state')} cycles_done={st.get('cycles_done')}", flush=True)

    mon = st.get("last_cycle_monitor") or st.get("first_cycle_monitor")
    if mon:
        print(
            f"[WATCH] monitor cycle={mon.get('cycle')} ok={mon.get('ok')} "
            f"exit={mon.get('exit_code')}",
            flush=True,
        )

    rep = load_monitor_report(focus)
    if rep:
        print(
            json.dumps(
                {
                    "monitor_ok": rep.get("ok"),
                    "cycle": rep.get("cycle"),
                    "passed": rep.get("passed"),
                    "failed": rep.get("failed"),
                    "experiment": rep.get("experiment"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    hist = list_monitor_history(focus, limit=3)
    if hist:
        print(f"[WATCH] history last={hist[-1]}", flush=True)

    return 0 if code == 0 and (rep or {}).get("ok", False) else (1 if code != 0 else 2)


if __name__ == "__main__":
    sys.exit(main())
