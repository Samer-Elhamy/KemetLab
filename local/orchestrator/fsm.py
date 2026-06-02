"""FSM state machine with JSON schema validation."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

import jsonschema

from local.llm.ollama_client import generate_fsm_json
from local.memory.graph_store import GraphStore
from local.memory.retrieve import build_prompt


class FSMState(str, Enum):
    RETRIEVE = "retrieve"
    PROPOSE = "propose"
    PEER_REVIEW = "peer_review"
    EXECUTE = "execute"
    INGEST = "ingest"
    UPDATE_GRAPH = "update_graph"
    DONE = "done"


def _load_schema(name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "schemas" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_payload(name: str, data: dict[str, Any]) -> None:
    schema = _load_schema(name)
    jsonschema.validate(instance=data, schema=schema)


def run_propose(graph: GraphStore, task_spec: str) -> dict[str, Any]:
    system, prompt = build_prompt("propose", graph, task_spec)
    raw = generate_fsm_json(prompt, system, tier="auto", fsm_state="propose")
    if raw.get("status") == "error":
        return raw
    validate_payload("proposal", raw)
    return raw


def run_peer_review(
    graph: GraphStore,
    task_spec: str,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    system, prompt = build_prompt("peer_review", graph, task_spec, proposal=proposal)
    raw = generate_fsm_json(prompt, system, tier="auto", fsm_state="peer_review")
    if raw.get("status") == "error":
        return {"approved": False, "reasons": [raw.get("reason", "LLM error")]}
    if "approved" not in raw:
        raw = generate_fsm_json(
            json.dumps(proposal),
            "Return JSON: approved boolean and reasons array.",
            tier="auto",
            fsm_state="json_repair",
        )
    validate_payload("peer_review", raw)
    return raw
