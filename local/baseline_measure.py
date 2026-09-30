"""Measure a real val_loss baseline by running task/repo/train.py once."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_PARAMS = {"lr": 0.1, "hidden_dim": 8, "steps": 10}

# Values at or above this are bootstrap placeholders, not real training results.
PLACEHOLDER_VAL_LOSS = 50.0


def is_placeholder_baseline(baseline: dict[str, Any]) -> bool:
    loss = float(baseline.get("val_loss", PLACEHOLDER_VAL_LOSS))
    source = str(baseline.get("source", ""))
    if loss >= PLACEHOLDER_VAL_LOSS:
        return True
    return source in ("bootstrap", "default", "placeholder")


def _kaggle_exec_mode() -> bool:
    return os.environ.get("AUTOSCIENTISTS_EXEC_MODE", "local").strip().lower() == "kaggle"


def _seed_kaggle_baseline(
    focus_root: Path,
    params: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    """Seed champion without local train (heavy work must run on Kaggle GPUs)."""
    # Default assumes ~0.82 OOF pair-AP proxy => val_loss = 1 - ap
    seed_loss = float(os.environ.get("AUTOSCIENTISTS_SEED_VAL_LOSS", "0.18"))
    baseline = {
        "val_loss": seed_loss,
        "params": params,
        "direction": "minimize",
        "source": source or "kaggle_seed_no_local_train",
        "exp_id": "seed_baseline",
        "note": "Baseline seeded; first measured metric comes from Kaggle kernel output.",
    }
    log_dir = focus_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "baseline.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    (focus_root / "champion.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    print(
        f"[baseline] Kaggle mode — seeded champion val_loss={seed_loss} (no local train)",
        flush=True,
    )
    return baseline


def run_train_for_params(focus_root: Path, params: dict[str, Any]) -> dict[str, Any]:
    focus_root = Path(focus_root).resolve()
    if _kaggle_exec_mode():
        raise RuntimeError(
            "Local train.py blocked: AUTOSCIENTISTS_EXEC_MODE=kaggle. "
            "Use remote Kaggle kernels for training."
        )
    train_py = focus_root / "task" / "repo" / "train.py"
    if not train_py.exists():
        train_py = focus_root / "repo" / "train.py"
    if not train_py.exists():
        raise FileNotFoundError(f"No train.py under {focus_root}")

    env = {
        **dict(os.environ),
        "SMOKE_LR": str(params.get("lr", 0.1)),
        "SMOKE_HIDDEN": str(params.get("hidden_dim", 8)),
        "SMOKE_STEPS": str(params.get("steps", 10)),
    }
    proc = subprocess.run(
        [sys.executable, str(train_py)],
        cwd=str(train_py.parent),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"train.py failed: {proc.stderr[:500]}")
    for line in proc.stdout.splitlines():
        if line.strip().startswith("{"):
            return json.loads(line.strip())
    raise RuntimeError(f"No JSON in train output: {proc.stdout[:300]}")


def measure_and_save_baseline(
    focus_root: Path,
    params: dict[str, Any] | None = None,
    *,
    source: str = "measured_at_bootstrap",
) -> dict[str, Any]:
    focus_root = Path(focus_root).resolve()
    params = params or DEFAULT_PARAMS.copy()
    if _kaggle_exec_mode():
        return _seed_kaggle_baseline(
            focus_root,
            params,
            source="kaggle_seed_no_local_train",
        )
    result = run_train_for_params(focus_root, params)
    baseline = {
        "val_loss": float(result["val_loss"]),
        "params": params,
        "direction": "minimize",
        "source": source,
        "exp_id": result.get("exp_id"),
    }
    log_dir = focus_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "baseline.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    # Champion starts at the real baseline until a KEEP beats it.
    (focus_root / "champion.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    return baseline


def ensure_measured_baseline(focus_root: Path) -> dict[str, Any]:
    """Load baseline; re-measure if still a placeholder (fixes old runs)."""
    focus_root = Path(focus_root).resolve()
    path = focus_root / "logs" / "baseline.json"
    if path.exists():
        baseline = json.loads(path.read_text(encoding="utf-8"))
        src = str(baseline.get("source", ""))
        if src.startswith("kaggle_seed") or not is_placeholder_baseline(baseline):
            return baseline
        params = baseline.get("params") or DEFAULT_PARAMS
    else:
        params = DEFAULT_PARAMS
    return measure_and_save_baseline(focus_root, params, source="measured_recalibrated")
