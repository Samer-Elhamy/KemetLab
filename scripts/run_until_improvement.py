#!/usr/bin/env python3
"""Run guided FSM cycles until val_loss improves vs baseline by target % (default 85)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.dashboard.cycle_metrics import _pct_improve, load_baseline
from local.dashboard.job_status import read_job_status, write_job_status
from local.orchestrator import promotion
from local.orchestrator.runner import run_iteration


def _log_autorun(run_dir: Path, record: dict) -> None:
    path = run_dir / "logs" / "autorun.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _champion_loss(run_dir: Path) -> float:
    ch = promotion.load_champion_json(run_dir)
    return float(ch.get("val_loss", float("inf")))


def _improvement_pct(run_dir: Path) -> float | None:
    baseline = load_baseline(run_dir)
    base_loss = float(baseline["val_loss"])
    champ_loss = _champion_loss(run_dir)
    return _pct_improve(base_loss, champ_loss, baseline.get("direction", "minimize"))


def _next_cycle(run_dir: Path) -> int:
    st = read_job_status(run_dir)
    if st.get("next_cycle"):
        return int(st["next_cycle"])
    exp_path = run_dir / "logs" / "experiments.jsonl"
    if not exp_path.exists():
        return 1
    mx = 0
    for line in exp_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            mx = max(mx, int(json.loads(line).get("cycle", 0)))
        except json.JSONDecodeError:
            continue
    return mx + 1


def _configure_env() -> None:
    os.environ.pop("LOCAL_MOCK_LLM", None)
    os.environ["LOCAL_TEAM_MODE"] = "0"
    os.environ["LOCAL_PROPOSE_MODE"] = os.environ.get("LOCAL_PROPOSE_MODE", "guided")
    os.environ["LOCAL_PEER_REVIEW"] = os.environ.get("LOCAL_PEER_REVIEW", "local")
    os.environ.setdefault("LOCAL_LLM_PROVIDER", "openrouter")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cycles until baseline improvement target.")
    parser.add_argument("--focus-root", type=Path, required=True)
    parser.add_argument("--target-pct", type=float, default=85.0, help="Min %% improve vs baseline")
    parser.add_argument("--max-cycles", type=int, default=500, help="Safety cap")
    parser.add_argument("--pause", type=float, default=1.0, help="Seconds between cycles")
    parser.add_argument("--monitor", action="store_true", help="Launch cycle monitor after each cycle")
    args = parser.parse_args()

    focus_root = Path(args.focus_root).resolve()
    if not focus_root.is_dir():
        print(f"focus-root not found: {focus_root}", file=sys.stderr)
        return 1

    _configure_env()
    baseline = load_baseline(focus_root)
    base_loss = float(baseline["val_loss"])
    target_loss = base_loss * (1.0 - args.target_pct / 100.0)

    cycle = _next_cycle(focus_root)
    st = read_job_status(focus_root)
    st.update(
        {
            "state": "running",
            "autorun": True,
            "autorun_target_pct": args.target_pct,
            "autorun_started_at": datetime.now(timezone.utc).isoformat(),
            "current_cycle": cycle,
            "goal_pct": args.target_pct,
        }
    )
    write_job_status(focus_root, st)

    print(
        f"[autorun] baseline val_loss={base_loss:.6f} "
        f"target>={args.target_pct:.1f}% (champion val_loss <= {target_loss:.6f})"
    )
    print(f"[autorun] starting cycle {cycle}, max {args.max_cycles} cycles")

    ran = 0
    try:
        while ran < args.max_cycles:
            imp = _improvement_pct(focus_root)
            if imp is not None and imp >= args.target_pct:
                print(f"[autorun] TARGET REACHED: {imp:.2f}% >= {args.target_pct}%")
                break

            imp_now = f"{imp:.2f}%" if imp is not None else "n/a"
            print(f"\n{'=' * 60}\nCYCLE {cycle} (improvement now: {imp_now})\n{'=' * 60}")
            st = read_job_status(focus_root)
            st["current_cycle"] = cycle
            st["current_phase"] = "autorun"
            write_job_status(focus_root, st)

            result = run_iteration(focus_root, cycle=cycle)
            champ_loss = _champion_loss(focus_root)
            imp = _improvement_pct(focus_root)
            imp_s = f"{imp:.2f}" if imp is not None else "n/a"

            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "cycle": cycle,
                "outcome": result.get("outcome"),
                "val_loss": result.get("val_loss"),
                "champion_val_loss": champ_loss,
                "improve_vs_baseline_pct": imp,
                "target_pct": args.target_pct,
            }
            _log_autorun(focus_root, record)
            print(
                f"[autorun] cycle {cycle} {result.get('outcome')} "
                f"val_loss={result.get('val_loss')} champion={champ_loss:.6f} improve={imp_s}%"
            )

            if args.monitor:
                try:
                    from local.dashboard.cycle_monitor import launch_cycle_monitor

                    launch_cycle_monitor(focus_root, cycle=cycle, wait=False)
                except Exception as e:
                    print(f"[autorun] monitor skip: {e}")

            if imp is not None and imp >= args.target_pct:
                print(f"[autorun] TARGET REACHED after cycle {cycle}: {imp:.2f}%")
                break

            ran += 1
            cycle += 1
            if args.pause > 0:
                time.sleep(args.pause)
    finally:
        imp = _improvement_pct(focus_root)
        st = read_job_status(focus_root)
        st.update(
            {
                "state": "complete" if (imp is not None and imp >= args.target_pct) else "stopped",
                "autorun": False,
                "autorun_finished_at": datetime.now(timezone.utc).isoformat(),
                "autorun_improve_pct": imp,
                "autorun_target_pct": args.target_pct,
                "next_cycle": cycle,
                "last_cycle": cycle - 1,
                "champion_val_loss": _champion_loss(focus_root),
            }
        )
        if imp is not None and imp >= args.target_pct:
            st["stop_reason"] = f"Reached {imp:.1f}% improvement (target {args.target_pct}%)"
        else:
            st["stop_reason"] = (
                f"Stopped after {ran} cycles at {imp:.1f}% "
                f"(target {args.target_pct}%, max_cycles={args.max_cycles})"
                if imp is not None
                else f"Stopped after {ran} cycles (max_cycles={args.max_cycles})"
            )
        write_job_status(focus_root, st)

    imp = _improvement_pct(focus_root)
    print(f"\n[autorun] done. improvement={imp:.2f}% champion={_champion_loss(focus_root):.6f}")
    return 0 if (imp is not None and imp >= args.target_pct) else 1


if __name__ == "__main__":
    raise SystemExit(main())
