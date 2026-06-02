"""Commit notebook shard syntheses to permanent graph nodes."""

from __future__ import annotations

from typing import Any

from local.memory.graph_store import GraphStore


def commit_shard_synthesis(
    store: GraphStore,
    shard_id: str,
    fsm_state: str,
    synthesis: dict[str, Any],
    block_summary_id: str | None = None,
) -> str:
    node_id = f"shard_{shard_id}_{fsm_state}"
    data = {
        "shard_id": shard_id,
        "fsm_state": fsm_state,
        "synthesis": synthesis,
    }
    store.add_node(node_id, "ShardSynthesis", data)
    if block_summary_id:
        store.add_edge(node_id, block_summary_id, "summarizes_shard")
    return node_id
