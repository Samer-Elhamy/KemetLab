#!/usr/bin/env python3
"""Standalone post-cycle monitor (invoked by run_job after each cycle)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.dashboard.cycle_monitor import run_cycle_monitor  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify mission health after a completed cycle.")
    parser.add_argument("--focus-root", type=Path, required=True)
    parser.add_argument("--cycle", type=int, default=1)
    parser.add_argument("--log-file", type=Path, default=None)
    args = parser.parse_args()

    if args.log_file:
        log_path = args.log_file.resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "a", encoding="utf-8")
        sys.stdout = log_handle
        sys.stderr = log_handle

    focus_root = args.focus_root.resolve()
    print(f"[MONITOR] start cycle={args.cycle} root={focus_root}", flush=True)
    summary = run_cycle_monitor(focus_root, cycle=args.cycle)
    print(
        f"[MONITOR] done ok={summary.get('ok')} "
        f"passed={summary.get('passed')} failed={summary.get('failed')}",
        flush=True,
    )
    if not summary.get("ok"):
        for c in summary.get("checks", []):
            if c.get("status") == "fail":
                line = f"[MONITOR] FAIL {c['name']}: {c.get('detail', '')}"
                try:
                    print(line, flush=True)
                except UnicodeEncodeError:
                    print(line.encode("ascii", errors="replace").decode(), flush=True)
    print(json.dumps({"monitor_ok": summary.get("ok"), "cycle": args.cycle}), flush=True)
    return 0 if summary.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
