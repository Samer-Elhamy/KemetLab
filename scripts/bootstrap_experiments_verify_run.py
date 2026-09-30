#!/usr/bin/env python3
"""Bootstrap experiments verify run directory."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXP = Path(r"C:\Users\Samer\AutoScientists-Local-Experiments")
RUN = Path(r"C:\Users\Samer\experiments_verify_0603")

sys.path.insert(0, str(REPO))
from local.launch_local import bootstrap_local_run

bootstrap_local_run(EXP, RUN, REPO / "task-experiments-verify", "optimization")
print("bootstrapped", RUN)
