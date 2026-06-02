"""Difficulty scoring for qwen35custom tier routing (heavy 9B vs light 0.8B)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local.llm import qwen35custom

CHARS_PER_TOKEN = 4


@dataclass
class DifficultyDecision:
    tier: str  # "heavy" | "light"
    score: float  # 0.0 = trivial, 1.0 = complex
    reason: str
    fsm_state: str
    model: str


def _est_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _difficulty_config(cfg: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "heavy_threshold": 0.55,
        "light_threshold": 0.35,
        "force_heavy_states": ["propose", "research_chat"],
        "force_light_states": ["json_repair", "block_summary", "shard_synthesis"],
        "heavy_keywords": [
            "hypothesis",
            "champion",
            "dead_end",
            "refactor",
            "graph",
            "proposal",
        ],
    }
    merged = {**defaults, **(cfg.get("difficulty") or {})}
    return merged


def score_difficulty(
    fsm_state: str,
    prompt: str,
    system_instruction: str = "",
    *,
    force_heavy: bool = False,
    config_path: Path | None = None,
) -> DifficultyDecision:
    """
    Map an FSM call to Tier-1 (heavy) or Tier-2 (light) based on task complexity.
    """
    cfg = load_routing_config(config_path)
    diff = _difficulty_config(cfg)
    text = f"{system_instruction}\n{prompt}"
    tokens = _est_tokens(text)
    state = fsm_state.replace("-", "_")

    if force_heavy or state in diff["force_heavy_states"]:
        score = 0.85
        tier = "heavy"
        reason = f"force_heavy:{state}"
    elif state in diff["force_light_states"]:
        score = 0.2
        tier = "light"
        reason = f"force_light:{state}"
    else:
        score = 0.4
        # Token volume
        if tokens > 2800:
            score += 0.35
        elif tokens > 1200:
            score += 0.2
        elif tokens < 500:
            score -= 0.15

        # State-specific
        if state == "peer_review":
            score += 0.15 if tokens > 900 else -0.1

        # Keyword density
        lower = text.lower()
        hits = sum(1 for k in diff["heavy_keywords"] if k in lower)
        score += min(0.25, hits * 0.08)

        score = max(0.0, min(1.0, score))
        heavy_threshold = float(diff["heavy_threshold"])
        light_threshold = float(diff["light_threshold"])
        if score >= heavy_threshold:
            tier = "heavy"
            reason = f"score={score:.2f}>={heavy_threshold}"
        elif score <= light_threshold:
            tier = "light"
            reason = f"score={score:.2f}<={light_threshold}"
        else:
            tier = "heavy" if state in ("peer_review", "propose") else "light"
            reason = f"score={score:.2f}_borderline->{tier}"

    model = qwen35custom.resolve_model(fsm_state, tier=tier, config_path=config_path)
    return DifficultyDecision(
        tier=tier,
        score=score,
        reason=reason,
        fsm_state=fsm_state,
        model=model,
    )


def load_routing_config(config_path: Path | None = None) -> dict[str, Any]:
    return qwen35custom.load_routing(config_path)
