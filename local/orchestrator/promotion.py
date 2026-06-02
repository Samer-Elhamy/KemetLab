"""Champion promotion for smoke / optimization tasks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def load_champion_json(focus_root: Path) -> dict[str, Any]:
    path = focus_root / "champion.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"val_loss": float("inf"), "params": {}, "direction": "minimize"}


def save_champion_json(focus_root: Path, data: dict[str, Any]) -> None:
    path = focus_root / "champion.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def promote_if_improved(
    focus_root: Path,
    val_loss: float,
    params: dict[str, Any],
    train_artifact: Path | None = None,
) -> bool:
    champ = load_champion_json(focus_root)
    direction = champ.get("direction", "minimize")
    improved = val_loss < champ.get("val_loss", float("inf")) if direction == "minimize" else val_loss > champ.get("val_loss", float("-inf"))

    if not improved:
        return False

    save_champion_json(
        focus_root,
        {"val_loss": val_loss, "params": params, "direction": direction},
    )
    champ_dir = focus_root / "champion"
    champ_dir.mkdir(exist_ok=True)
    if train_artifact and train_artifact.exists():
        shutil.copy2(train_artifact, champ_dir / "train.py")
    return True
