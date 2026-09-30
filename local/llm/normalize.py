"""Normalize cloud LLM JSON into FSM schema shapes."""

from __future__ import annotations

from typing import Any


def normalize_proposal(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("status") == "error":
        return raw
    if "params" in raw and isinstance(raw.get("params"), dict):
        raw.setdefault("hypothesis", raw.get("hypothesis") or "Cloud model proposal")
        raw.setdefault("rationale", raw.get("rationale") or "")
        return raw
  # Flat: {lr, hidden_dim, steps}
    keys = ("lr", "hidden_dim", "steps")
    if any(k in raw for k in keys):
        params = {k: raw[k] for k in keys if k in raw}
        return {
            "hypothesis": str(raw.get("hypothesis") or "Optimize hyperparameters for val_loss"),
            "params": params,
            "rationale": str(raw.get("rationale") or "normalized from flat LLM output"),
        }
    return raw


def normalize_peer_review(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("status") == "error":
        return raw
    if "approved" in raw:
        return raw
    if raw.get("approve") is not None:
        return {"approved": bool(raw["approve"]), "reasons": raw.get("reasons", [])}
    return {"approved": True, "reasons": ["normalized default approve"]}
