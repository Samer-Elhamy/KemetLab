"""Tier routing for the qwen35custom Ollama gateway."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROUTING_CACHE: dict[str, Any] | None = None

DEFAULT_ROUTING = {
    "gateway": "qwen35custom",
    "tiers": {
        "heavy": "qwen3.5-9b-gguf:ud-q4_k_xl",
        "light": "qwen3.5:0.8b-gguf",
    },
    "routing": {
        "propose": "heavy",
        "peer_review": "heavy",
        "json_repair": "light",
        "block_summary": "light",
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
    """Return Ollama model tag for gateway or resolved tier backend."""
    cfg = load_routing(config_path)
    tiers = cfg.get("tiers", DEFAULT_ROUTING["tiers"])
    routing = cfg.get("routing", DEFAULT_ROUTING["routing"])
    gateway = cfg.get("gateway", "qwen35custom")

    if tier == "heavy":
        return tiers.get("heavy", DEFAULT_ROUTING["tiers"]["heavy"])
    if tier == "light":
        return tiers.get("light", DEFAULT_ROUTING["tiers"]["light"])

    route_key = fsm_state.replace("-", "_")
    tier_name = routing.get(route_key, routing.get(fsm_state, "heavy"))
    return tiers.get(tier_name, gateway)


def gateway_name(config_path: Path | None = None) -> str:
    return load_routing(config_path).get("gateway", "qwen35custom")
