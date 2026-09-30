"""Load API keys from env or local config files (never log values)."""

from __future__ import annotations

import os
from pathlib import Path


def _parse_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val


def bootstrap_env() -> None:
    """Fill os.environ from common key locations."""
    repo = Path(__file__).resolve().parents[2]
    paths = [
        repo / ".env",
        repo / "local" / "config" / "openrouter.key",
        Path.home() / ".hermes" / ".env",
        Path.home() / ".env",
    ]
    for p in paths:
        if p.suffix == ".key" and p.is_file():
            os.environ.setdefault("OPENROUTER_API_KEY", p.read_text(encoding="utf-8").strip())
        else:
            _parse_env_file(p)


def openrouter_api_key() -> str | None:
    bootstrap_env()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    return key or None
