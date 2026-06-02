"""Ingest experiment results into the graph."""

from __future__ import annotations

import uuid
from typing import Any

from local.memory.graph_store import GraphStore


def ingest_experiment(
    store: GraphStore,
    proposal: dict[str, Any],
    result: dict[str, Any],
    exp_id: str | None = None,
) -> str:
    exp_id = exp_id or f"exp_{uuid.uuid4().hex[:8]}"
    store.add_node(
        f"proposal_{exp_id}",
        "Proposal",
        {"exp_id": exp_id, **proposal},
    )
    store.add_node(
        f"result_{exp_id}",
        "Result",
        {"exp_id": exp_id, **result},
    )
    store.add_edge(f"proposal_{exp_id}", f"result_{exp_id}", "tests")
    if store.get_node("champion"):
        store.add_edge(f"result_{exp_id}", "champion", "supports")
    return exp_id


def ensure_champion(store: GraphStore, val_loss: float, params: dict[str, Any]) -> None:
    existing = store.get_node("champion")
    if existing is None:
        store.add_node(
            "champion",
            "Champion",
            {"val_loss": val_loss, "params": params, "direction": "minimize"},
        )
        return
    if val_loss < existing.get("val_loss", float("inf")):
        store.add_node(
            "champion",
            "Champion",
            {"val_loss": val_loss, "params": params, "direction": "minimize"},
        )


def add_dead_end(store: GraphStore, reason: str) -> str:
    de_id = f"dead_{uuid.uuid4().hex[:8]}"
    store.add_node(de_id, "DeadEnd", {"reason": reason})
    if store.get_node("champion"):
        store.add_edge(de_id, "champion", "refutes")
    return de_id
