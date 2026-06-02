"""Kimi context sharding — isolated notebook buffers per FSM state."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NotebookShard:
    shard_id: str
    fsm_state: str
    content: str = ""
    synthesis: dict[str, Any] = field(default_factory=dict)

    def append(self, text: str) -> None:
        self.content += text


def create_shard(fsm_state: str, initial: str = "") -> NotebookShard:
    return NotebookShard(
        shard_id=f"shard_{uuid.uuid4().hex[:10]}",
        fsm_state=fsm_state,
        content=initial,
    )


def synthesize_shard_light(shard: NotebookShard) -> dict[str, Any]:
    """Deterministic micro-synthesis (Tier-2 would refine via LLM in full mode)."""
    return {
        "state": shard.fsm_state,
        "chars": len(shard.content),
        "summary": shard.content[:500] if shard.content else "(empty)",
    }
