"""AttnRes-style block lifecycle and summary eviction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from local.memory.graph_store import GraphStore


@dataclass
class BlockContext:
    block_id: str
    raw_logs: list[str] = field(default_factory=list)
    states_completed: list[str] = field(default_factory=list)

    def append_log(self, text: str) -> None:
        self.raw_logs.append(text)

    def mark_state(self, state: str) -> None:
        self.states_completed.append(state)


def open_block() -> BlockContext:
    return BlockContext(block_id=f"block_{uuid.uuid4().hex[:12]}")


def close_block(
    store: GraphStore,
    block: BlockContext,
    summary: dict[str, Any],
    champion_before: float,
    champion_after: float,
) -> str:
    """Persist block summary node and evict raw logs from active memory."""
    node_id = f"summary_{block.block_id}"
    summary.setdefault("block_id", block.block_id)
    summary.setdefault("fsm_states_completed", block.states_completed)
    summary.setdefault("champion_metric_before", champion_before)
    summary.setdefault("champion_metric_after", champion_after)
    store.add_node(node_id, "BlockSummary", summary)
    if store.get_node("champion"):
        store.add_edge(node_id, "champion", "summarizes_block")
    block.raw_logs.clear()
    return node_id


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
