"""Optional Hermes Agent routing adapter (Phase 4). Stub for future integration."""

from __future__ import annotations


def available() -> bool:
    return False


def route_to_ollama(prompt: str, complexity: str = "standard") -> str:
    raise NotImplementedError("Hermes adapter is optional; use qwen35custom gateway directly.")
