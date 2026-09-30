"""Per-cycle results and honest improvement % (real train.py baseline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from local.baseline_measure import ensure_measured_baseline, is_placeholder_baseline
from local.dashboard.data import load_champion, read_jsonl

DEFAULT_PARAMS = {"lr": 0.1, "hidden_dim": 8, "steps": 10}


def load_baseline(run_dir: Path) -> dict[str, Any]:
    return ensure_measured_baseline(run_dir)


def save_baseline_if_missing(run_dir: Path, baseline: dict[str, Any] | None = None) -> None:
    path = run_dir / "logs" / "baseline.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not is_placeholder_baseline(existing):
            return
    from local.baseline_measure import measure_and_save_baseline

    measure_and_save_baseline(run_dir, (baseline or {}).get("params") or DEFAULT_PARAMS)


def _pick_cycle_row(group: list[dict[str, Any]]) -> dict[str, Any]:
    keeps = [g for g in group if g.get("outcome") == "KEEP"]
    if keeps:
        return min(keeps, key=lambda g: float(g.get("val_loss", float("inf"))))
    return max(group, key=lambda g: g.get("ts", ""))


def _one_row_per_cycle(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        if "cycle" not in r:
            continue
        groups.setdefault(int(r["cycle"]), []).append(r)
    return [_pick_cycle_row(groups[c]) for c in sorted(groups)]


def _pct_improve(before: float, after: float, direction: str = "minimize") -> float | None:
    if before is None or after is None:
        return None
    if direction == "minimize":
        if before <= 0:
            return None
        return (before - after) / before * 100.0
    if after <= 0:
        return None
    return (after - before) / before * 100.0


def cycle_results_df(run_dir: Path) -> pd.DataFrame:
    run_dir = Path(run_dir)
    save_baseline_if_missing(run_dir)
    baseline = load_baseline(run_dir)
    direction = baseline.get("direction", "minimize")
    base_loss = float(baseline["val_loss"])

    rows = _one_row_per_cycle(read_jsonl(run_dir / "logs" / "experiments.jsonl"))
    if not rows:
        return pd.DataFrame(
            columns=[
                "cycle",
                "val_loss",
                "outcome",
                "improve_vs_baseline_pct",
                "improve_vs_prev_champion_pct",
                "champion_after",
            ]
        )

    champion_loss = base_loss
    out_rows: list[dict[str, Any]] = []

    for r in rows:
        cycle = int(r["cycle"])
        val_loss = float(r.get("val_loss", 0))
        outcome = r.get("outcome", "?")
        imp_base = _pct_improve(base_loss, val_loss, direction)
        imp_prev = _pct_improve(champion_loss, val_loss, direction)

        if direction == "minimize":
            if outcome == "KEEP" and val_loss < champion_loss:
                champion_loss = val_loss
        elif outcome == "KEEP" and val_loss > champion_loss:
            champion_loss = val_loss

        params = r.get("params") or {}
        out_rows.append(
            {
                "cycle": cycle,
                "exp_id": r.get("exp_id", ""),
                "val_loss": val_loss,
                "outcome": outcome,
                "improve_vs_baseline_pct": round(imp_base, 2) if imp_base is not None else None,
                "improve_vs_prev_champion_pct": round(imp_prev, 2) if imp_prev is not None else None,
                "champion_after": champion_loss,
                "lr": params.get("lr"),
                "hidden_dim": params.get("hidden_dim"),
                "steps": params.get("steps"),
                "ts": r.get("ts"),
            }
        )

    return pd.DataFrame(out_rows)


def run_improvement_summary(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    save_baseline_if_missing(run_dir)
    baseline = load_baseline(run_dir)
    champ = load_champion(run_dir)
    direction = baseline.get("direction", "minimize")
    base_loss = float(baseline["val_loss"])
    current = float(champ.get("val_loss", base_loss))

    total_pct = _pct_improve(base_loss, current, direction)
    df = cycle_results_df(run_dir)
    n_cycles = len(df)
    n_keep = (
        int((df["outcome"] == "KEEP").sum())
        if not df.empty and "outcome" in df.columns
        else 0
    )

    source = baseline.get("source", "measured")
    baseline_note = (
        "تدريب فعلي بمعاملات البداية (lr/hidden/steps)"
        if "measured" in str(source)
        else str(source)
    )

    return {
        "baseline_val_loss": base_loss,
        "baseline_params": baseline.get("params", {}),
        "baseline_note": baseline_note,
        "current_val_loss": current,
        "total_improvement_pct": round(total_pct, 2) if total_pct is not None else None,
        "direction": direction,
        "cycles_completed": n_cycles,
        "keep_count": n_keep,
        "executed": n_cycles > 0,
        "honest_metrics": True,
    }
