"""Role-routed prompt assembly with skip connections (≤4096 token budget)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from local.memory.graph_store import GraphStore

MAX_PROMPT_TOKENS = 4096
CHARS_PER_TOKEN_EST = 4


def _est_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN_EST)


def task_spec_excerpt(task_spec: str, max_tokens: int = 512) -> str:
    max_chars = max_tokens * CHARS_PER_TOKEN_EST
    if len(task_spec) <= max_chars:
        return task_spec
    return task_spec[:max_chars] + "\n...[truncated]"


def truncate_to_budget(anchor: str, body: str, max_tokens: int = MAX_PROMPT_TOKENS) -> str:
    combined = anchor + "\n\n" + body
    budget_chars = max_tokens * CHARS_PER_TOKEN_EST
    if len(combined) <= budget_chars:
        return combined
    # Preserve anchor; trim body
    anchor_chars = len(anchor) + 2
    body_budget = max(0, budget_chars - anchor_chars)
    return anchor + "\n\n" + (body[:body_budget] + "\n...[truncated]")


def global_context(graph: GraphStore, k_blocks: int = 3, k_nodes: int = 8) -> str:
    parts = []
    champ = graph.get_node("champion")
    if champ:
        parts.append(
            "Champion (beat this val_loss): "
            f"val_loss={champ.get('val_loss')} params={champ.get('params')}. "
            "Do NOT repeat lr=0.01, hidden_dim=32, steps=50."
        )
    for de in graph.nodes_by_kind("DeadEnd", limit=k_nodes):
        parts.append(f"DeadEnd: {de.get('reason', de)}")
    for summ in graph.nodes_by_kind("BlockSummary", limit=k_blocks):
        findings = summ.get("key_findings", [])
        parts.append(f"Block {summ.get('block_id')}: {findings}")
    return "\n".join(parts) if parts else "No prior graph context."


def local_context(graph: GraphStore, proposal: dict[str, Any], block_id: str | None = None) -> str:
    parts = [f"Proposal: {proposal}"]
    champ = graph.get_node("champion")
    if champ:
        parts.append(f"Current champion val_loss={champ.get('val_loss')}")
    return "\n".join(parts)


def system_from_prompts_dir(fsm_state: str, prompts_dir: Path | None = None) -> str:
    prompts_dir = prompts_dir or Path(__file__).resolve().parents[1] / "prompts"
    name = {"propose": "worker_propose.txt", "peer_review": "worker_review.txt"}.get(
        fsm_state, "worker_propose.txt"
    )
    path = prompts_dir / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_prompt(
    fsm_state: str,
    graph: GraphStore,
    task_spec: str,
    proposal: dict[str, Any] | None = None,
    block_id: str | None = None,
) -> tuple[str, str]:
    """Returns (system_instruction, user_prompt) with enforced skip-connection layout."""
    anchor = "## TASK (anchor)\n" + task_spec_excerpt(task_spec)

    if fsm_state == "propose":
        body = "## Global context\n" + global_context(graph)
    else:
        body = "## Local context\n" + local_context(graph, proposal or {}, block_id)

    user_prompt = truncate_to_budget(anchor, body)
    system = system_from_prompts_dir(fsm_state)
    if _est_tokens(user_prompt) > MAX_PROMPT_TOKENS + 64:
        user_prompt = truncate_to_budget(anchor, body[: MAX_PROMPT_TOKENS * CHARS_PER_TOKEN_EST])
    return system, user_prompt
