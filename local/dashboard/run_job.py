#!/usr/bin/env python3
"""Background FSM job for dashboard (long runs, agent tracking, graceful stop)."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from local.dashboard.repo_root import find_repo_root, ensure_repo_on_syspath

_REPO = ensure_repo_on_syspath()

from local.dashboard.job_status import read_job_status, write_job_status  # noqa: E402

_write_status = write_job_status
from local.orchestrator import agent_tracker  # noqa: E402
from local.orchestrator.runner import run_iteration  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--focus-root", type=Path, required=True)
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=1,
        help="0 = unlimited (use with --max-hours)",
    )
    parser.add_argument("--cycle-start", type=int, default=1)
    parser.add_argument(
        "--max-hours",
        type=float,
        default=0,
        help="Stop after this many hours (0 = no time limit)",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=2.0,
        help="Pause between cycles (cooldown)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Append stdout/stderr to this log file",
    )
    args = parser.parse_args()

    if args.log_file:
        log_path = args.log_file.resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "a", encoding="utf-8")
        sys.stdout = log_handle
        sys.stderr = log_handle

    focus_root = args.focus_root.resolve()
    from local.dashboard.sync_runtime import sync_runtime_from_repo
    from local.orchestrator import agent_tracker as _at
    from local.orchestrator.team_manager import load_or_seed_roster

    sync_runtime_from_repo(focus_root, _REPO)
    if not hasattr(_at, "bootstrap_job_start"):
        import importlib

        importlib.reload(_at)
    agent_tracker = _at

    agent_tracker.clear_stop(focus_root)
    teams = load_or_seed_roster(focus_root)
    agent_tracker.bootstrap_job_start(
        focus_root, args.cycle_start, f"بدء دورات FSM — {len(teams)} فرق", teams=teams
    )

    st = read_job_status(focus_root)
    st["state"] = "running"
    if args.max_hours > 0:
        ends = datetime.now(timezone.utc) + timedelta(hours=args.max_hours)
        st["ends_at"] = ends.isoformat()
    _write_status(focus_root, st)

    started = time.time()
    deadline = started + args.max_hours * 3600 if args.max_hours > 0 else None
    cycle = args.cycle_start
    completed = 0

    try:
        while True:
            if agent_tracker.is_stop_requested(focus_root):
                st = read_job_status(focus_root)
                st.update(
                    {
                        "state": "stopped",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "stop_reason": "user_stop",
                        "cycles_done": completed,
                        "last_cycle": cycle - 1 if cycle > args.cycle_start else None,
                        "cycles_total": args.max_cycles if args.max_cycles > 0 else st.get("cycles_total"),
                    }
                )
                _write_status(focus_root, st)
                live = agent_tracker.read_live(focus_root)
                live["job_state"] = "stopped"
                agent_tracker.write_live(focus_root, live)
                agent_tracker.set_agent(
                    focus_root, "orchestrator", "done", "توقف بطلب المستخدم", cycle=max(cycle - 1, args.cycle_start)
                )
                return 0

            if deadline and time.time() >= deadline:
                break

            if args.max_cycles > 0 and completed >= args.max_cycles:
                break

            print(f"CYCLE {cycle}", flush=True)
            agent_tracker.set_agent(
                focus_root,
                "orchestrator",
                "working",
                f"الدورة {cycle} — تنسيق الفريق",
                cycle=cycle,
            )
            st = read_job_status(focus_root)
            st["current_cycle"] = cycle
            st["cycles_done"] = completed
            st["current_phase"] = f"بدء الدورة {cycle}"
            st["current_agent"] = "orchestrator"
            _write_status(focus_root, st)

            run_iteration(focus_root, cycle=cycle)
            completed += 1
            finished_cycle = cycle
            cycle += 1

            st = read_job_status(focus_root)
            st["cycles_done"] = completed
            st["last_cycle"] = finished_cycle
            elapsed_h = (time.time() - started) / 3600.0
            st["elapsed_hours"] = round(elapsed_h, 3)

            # Separate monitor process after each completed cycle
            from local.dashboard.cycle_monitor import launch_cycle_monitor

            st["current_phase"] = f"متابع الدورة {finished_cycle} — فحص النظام"
            st["current_agent"] = "orchestrator"
            _write_status(focus_root, st)
            mon = launch_cycle_monitor(
                focus_root,
                finished_cycle,
                template_dir=_REPO,
                log_path=args.log_file,
                wait=True,
                timeout_sec=120.0,
            )
            st["last_cycle_monitor"] = {**mon, "cycle": finished_cycle}
            if finished_cycle == args.cycle_start:
                st["first_cycle_monitor"] = st["last_cycle_monitor"]
            print(
                f"[MONITOR] cycle {finished_cycle} ok={mon.get('ok')} "
                f"exit={mon.get('exit_code')}",
                flush=True,
            )
            _write_status(focus_root, st)

            if args.max_cycles > 0 and completed >= args.max_cycles:
                break
            if deadline and time.time() >= deadline:
                break

            if args.pause_seconds > 0:
                agent_tracker.set_all_idle_except(
                    focus_root,
                    "orchestrator",
                    f"استراحة {args.pause_seconds:.0f}ث قبل الدورة {cycle}",
                    cycle,
                )
                st = read_job_status(focus_root)
                st["current_phase"] = f"استراحة بين الدورات ({args.pause_seconds:.0f}ث)"
                st["current_agent"] = "orchestrator"
                _write_status(focus_root, st)
                time.sleep(args.pause_seconds)

        st = read_job_status(focus_root)
        if args.max_cycles > 0 and completed >= args.max_cycles:
            final_state = "complete"
            stop_reason = None
        elif deadline and time.time() >= deadline:
            final_state = "stopped"
            stop_reason = "time_limit"
        else:
            final_state = "complete"
            stop_reason = None
        st.update(
            {
                "state": final_state,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "cycles_done": completed,
                "elapsed_hours": round((time.time() - started) / 3600.0, 3),
                "stop_reason": stop_reason,
            }
        )
        _write_status(focus_root, st)
        live = agent_tracker.read_live(focus_root)
        live["job_state"] = st["state"]
        agent_tracker.write_live(focus_root, live)
        return 0
    except Exception as exc:
        st = read_job_status(focus_root)
        st.update(
            {
                "state": "error",
                "error": str(exc),
                "traceback": traceback.format_exc()[-2000:],
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_status(focus_root, st)
        agent_tracker.set_agent(focus_root, "orchestrator", "error", str(exc)[:200])
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
