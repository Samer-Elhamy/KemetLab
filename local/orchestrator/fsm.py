"""FSM state machine with JSON schema validation."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

import jsonschema

from local.llm.normalize import normalize_peer_review, normalize_proposal
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


def run_propose(
    graph: GraphStore,
    task_spec: str,
    focus_root: Path | None = None,
    cycle: int = 1,
    *,
    team_offset: int = 0,
) -> dict[str, Any]:
    from local.orchestrator.param_search import guided_proposal, merge_llm_with_guided, propose_mode

    if propose_mode() in ("guided", "guide", "local") and focus_root is not None:
        raw = guided_proposal(focus_root, cycle, team_offset=team_offset)
        validate_payload("proposal", raw)
        return raw

    system, prompt = build_prompt("propose", graph, task_spec)
    llm_raw = normalize_proposal(
        generate_fsm_json(prompt, system, tier="auto", fsm_state="propose")
    )

    if focus_root is not None:
        raw = merge_llm_with_guided(
            focus_root, cycle, llm_raw, team_offset=team_offset
        )
    elif llm_raw.get("status") == "error":
        return llm_raw
    else:
        raw = llm_raw

    if raw.get("status") == "error":
        return raw
    validate_payload("proposal", raw)
    return raw


def _local_peer_review(proposal: dict[str, Any]) -> dict[str, Any] | None:
    import os

    if os.environ.get("LOCAL_PEER_REVIEW", "").lower() not in (
        "local",
        "1",
        "true",
        "skip_cloud",
    ):
        if proposal.get("source") != "guided" and os.environ.get(
            "LOCAL_PROPOSE_MODE", "hybrid"
        ).lower() not in ("guided", "guide", "local"):
            return None
    params = proposal.get("params") or {}
    try:
        lr = float(params.get("lr", 0.05))
        h = int(params.get("hidden_dim", params.get("max_depth", 6)))
        s = int(params.get("steps", params.get("n_estimators", 100)))
    except (KeyError, TypeError, ValueError):
        return {"approved": False, "reasons": ["missing or invalid params"]}
    if not (0.001 <= lr <= 0.2 and 4 <= h <= 256 and 5 <= s <= 1000):
        return {"approved": False, "reasons": ["params out of TASK search space"]}
    from local.orchestrator.param_search import is_stale_mock_params

    if is_stale_mock_params(params):
        return {"approved": False, "reasons": ["stale mock fingerprint rejected"]}
    return {
        "approved": True,
        "reasons": ["local bounds check — skip cloud peer review"],
    }


def run_peer_review(
    graph: GraphStore,
    task_spec: str,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    local = _local_peer_review(proposal)
    if local is not None:
        return local

    system, prompt = build_prompt("peer_review", graph, task_spec, proposal=proposal)
    raw = normalize_peer_review(
        generate_fsm_json(prompt, system, tier="auto", fsm_state="peer_review")
    )
    if raw.get("status") == "error":
        return {"approved": False, "reasons": [raw.get("reason", "LLM error")]}
    if "approved" not in raw:
        raw = normalize_peer_review(
            generate_fsm_json(
                json.dumps(proposal),
                "Return JSON: approved boolean and reasons array.",
                tier="auto",
                fsm_state="json_repair",
            )
        )
    validate_payload("peer_review", raw)
    return raw
