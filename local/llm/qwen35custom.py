"""Tier routing for Google Gemini gateway (Heavy & Light)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_ROUTING_CACHE: dict[str, Any] | None = None

DEFAULT_ROUTING = {
    "gateway": "gemini",
    "tiers": {
        "heavy": "gemini-3.8-flash-high",
        "light": "gemini-3.8-flash-lite",
    },
    "routing": {
        "propose": "heavy",
        "peer_review": "heavy",
        "json_repair": "light",
        "block_summary": "light",
        "research_chat": "heavy",
    },
}


def load_routing(config_path: Path | None = None) -> dict[str, Any]:
    global _ROUTING_CACHE
    if _ROUTING_CACHE is not None:
        return _ROUTING_CACHE
    path = config_path or Path(__file__).resolve().parents[1] / "config" / "routing.yaml"
    if path.exists():
        _ROUTING_CACHE = yaml.safe_load(path.read_text()) or DEFAULT_ROUTING
    else:
        _ROUTING_CACHE = DEFAULT_ROUTING.copy()
    return _ROUTING_CACHE


def resolve_model(fsm_state: str, tier: str | None = None, config_path: Path | None = None) -> str:
    """Return Google Gemini model name for the requested tier."""
    cfg = load_routing(config_path)
    tiers = cfg.get("tiers", DEFAULT_ROUTING["tiers"])
    routing = cfg.get("routing", DEFAULT_ROUTING["routing"])

    if tier == "heavy":
        return os.environ.get("GEMINI_HEAVY_MODEL") or tiers.get(
            "heavy", "gemini-3.8-flash-high"
        )
    if tier == "light":
        return os.environ.get("GEMINI_LIGHT_MODEL") or tiers.get(
            "light", "gemini-3.1-flash-lite"
        )

    route_key = fsm_state.replace("-", "_")
    tier_name = routing.get(route_key, routing.get(fsm_state, "heavy"))
    return tiers.get(tier_name, "gemini-3.8-flash-high")


def gateway_name(config_path: Path | None = None) -> str:
    return "gemini"
