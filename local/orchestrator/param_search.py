"""Champion-guided hyperparameter proposals when LLM/mock returns stale params."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# Known-bad defaults from LOCAL_MOCK_LLM / Ollama fallback fingerprint
STALE_MOCK_PARAMS = {"lr": 0.01, "hidden_dim": 32, "steps": 50}

# Strong regions on smoke train.py (deterministic seed 42)
_SEARCH_ANCHORS: list[dict[str, float | int]] = [
    # PyTorch deep-fit region (reaches >99.8% vs smoke baseline)
    {"lr": 0.01, "hidden_dim": 64, "steps": 500},
    {"lr": 0.01, "hidden_dim": 64, "steps": 600},
    {"lr": 0.01, "hidden_dim": 64, "steps": 450},
    {"lr": 0.01, "hidden_dim": 64, "steps": 550},
    {"lr": 0.01, "hidden_dim": 64, "steps": 200},
    {"lr": 0.008, "hidden_dim": 64, "steps": 500},
    {"lr": 0.01, "hidden_dim": 128, "steps": 500},
    {"lr": 0.01, "hidden_dim": 48, "steps": 500},
    # Legacy numpy-friendly region
    {"lr": 0.2, "hidden_dim": 4, "steps": 100},
    {"lr": 0.2, "hidden_dim": 4, "steps": 30},
    {"lr": 0.15, "hidden_dim": 6, "steps": 25},
    {"lr": 0.2, "hidden_dim": 4, "steps": 61},
]


def _clamp_params(p: dict[str, Any]) -> dict[str, Any]:
    lr = max(0.001, min(0.2, float(p.get("lr", 0.1))))
    hidden = int(max(2, min(128, round(float(p.get("hidden_dim", 8))))))
    steps = int(max(5, min(1000, round(float(p.get("steps", 10))))))
    return {"lr": round(lr, 4), "hidden_dim": hidden, "steps": steps}


def load_champion_params(focus_root: Path) -> dict[str, Any]:
    path = Path(focus_root) / "champion.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        params = data.get("params") or {}
        if params:
            return _clamp_params(params)
    return {"lr": 0.1, "hidden_dim": 8, "steps": 10}


def is_stale_mock_params(params: dict[str, Any] | None) -> bool:
    if not params:
        return True
    try:
        return (
            abs(float(params.get("lr", -1)) - STALE_MOCK_PARAMS["lr"]) < 1e-9
            and int(params.get("hidden_dim", -1)) == STALE_MOCK_PARAMS["hidden_dim"]
            and int(params.get("steps", -1)) == STALE_MOCK_PARAMS["steps"]
        )
    except (TypeError, ValueError):
        return True


def _mutations(base: dict[str, Any]) -> list[dict[str, Any]]:
    lr, h, s = float(base["lr"]), int(base["hidden_dim"]), int(base["steps"])
    return [
        _clamp_params({"lr": lr * 1.25, "hidden_dim": h, "steps": s}),
        _clamp_params({"lr": lr * 0.8, "hidden_dim": h, "steps": s}),
        _clamp_params({"lr": lr, "hidden_dim": max(4, h - 2), "steps": s + 5}),
        _clamp_params({"lr": lr, "hidden_dim": h + 2, "steps": max(5, s - 3)}),
        _clamp_params({"lr": lr * 1.1, "hidden_dim": max(4, h - 4), "steps": s + 8}),
        _clamp_params({"lr": min(0.2, lr + 0.05), "hidden_dim": h, "steps": s + 10}),
    ]


def pick_guided_params(focus_root: Path, cycle: int, team_offset: int = 0) -> dict[str, Any]:
    """Deterministic params for this cycle — explores anchors then champion mutations."""
    base = load_champion_params(focus_root)
    mutations = _mutations(base)
    pool: list[dict[str, Any]] = list(_SEARCH_ANCHORS) + mutations
    idx = (max(1, int(cycle)) + int(team_offset)) % len(pool)
    return pool[idx]


def guided_proposal(
    focus_root: Path,
    cycle: int,
    *,
    team_offset: int = 0,
    reason: str = "champion-guided search",
) -> dict[str, Any]:
    params = pick_guided_params(focus_root, cycle, team_offset=team_offset)
    return {
        "hypothesis": f"Guided mutation cycle {cycle}: tune lr/hidden_dim/steps near champion",
        "params": params,
        "rationale": reason,
        "source": "guided",
    }


def propose_mode() -> str:
    import os

    return os.environ.get("LOCAL_PROPOSE_MODE", "hybrid").lower().strip()


def merge_llm_with_guided(
    focus_root: Path,
    cycle: int,
    llm_raw: dict[str, Any],
    *,
    team_offset: int = 0,
) -> dict[str, Any]:
    """Use LLM output only when it is valid and not the stale mock fingerprint."""
    mode = propose_mode()
    guided = guided_proposal(focus_root, cycle, team_offset=team_offset)

    if mode in ("guided", "guide", "local"):
        return guided

    if llm_raw.get("status") == "error":
        guided["rationale"] = f"LLM error — {llm_raw.get('reason', '')[:120]}"
        return guided

    params = llm_raw.get("params") if isinstance(llm_raw.get("params"), dict) else {}
    if mode == "llm" and params and not is_stale_mock_params(params):
        llm_raw.setdefault("source", "llm")
        return llm_raw

    if is_stale_mock_params(params) or not params:
        out = dict(guided)
        out["rationale"] = (
            "Replaced stale/mock LLM params with champion-guided search. "
            + str(llm_raw.get("rationale") or "")[:80]
        )
        return out

    if mode == "hybrid":
        llm_raw.setdefault("source", "llm")
        return llm_raw

    return llm_raw
