#!/usr/bin/env python3
"""Production track: guided smoke cycles until stagnation (runs in background)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.dashboard.cycle_metrics import _pct_improve, load_baseline
from local.dashboard.job_status import read_job_status, write_job_status
from local.orchestrator import promotion
from local.orchestrator.runner import run_iteration


def main() -> None:
    run_dir = Path(os.environ.get("PRODUCTION_RUN_DIR", r"C:\Users\Samer\dashboard_0602_174304"))
    os.environ.pop("LOCAL_MOCK_LLM", None)
    os.environ["LOCAL_TEAM_MODE"] = "0"
    os.environ["LOCAL_PROPOSE_MODE"] = "guided"
    os.environ["LOCAL_PEER_REVIEW"] = "local"

    baseline = float(load_baseline(run_dir)["val_loss"])
    st = read_job_status(run_dir)
    cycle = int(st.get("next_cycle") or 125)
    st.update({"state": "running", "track": "production", "dual_track": True, "pid": os.getpid()})
    write_job_status(run_dir, st)
    from local.orchestrator import agent_tracker

    agent_tracker.init_team(run_dir, cycle=cycle)

    stagnant = 0
    max_stagnant = int(os.environ.get("PRODUCTION_MAX_STAGNANT", "200"))
    while stagnant < max_stagnant:
        champ = float(promotion.load_champion_json(run_dir)["val_loss"])
        imp = _pct_improve(baseline, champ, "minimize") or 0
        result = run_iteration(run_dir, cycle=cycle)
        st = read_job_status(run_dir)
        st["current_cycle"] = cycle
        st["state"] = "running"
        st["track"] = "production"
        write_job_status(run_dir, st)
        if result.get("outcome") == "KEEP":
            stagnant = 0
        else:
            stagnant += 1
        cycle += 1
        time.sleep(1)

    st = read_job_status(run_dir)
    st.update(
        {
            "state": "complete",
            "track": "production",
            "next_cycle": cycle,
            "stop_reason": "production track stagnant or target",
        }
    )
    write_job_status(run_dir, st)


if __name__ == "__main__":
    main()
