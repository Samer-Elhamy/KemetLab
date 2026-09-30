"""Ollama client for FSM JSON generation with VRAM-safe tier routing."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from local.llm import qwen35custom
from local.llm.difficulty import DifficultyDecision, score_difficulty

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
GATEWAY_MODEL = qwen35custom.gateway_name()
TIER_HEAVY = qwen35custom.resolve_model("propose", tier="heavy")
TIER_LIGHT = qwen35custom.resolve_model("json_repair", tier="light")

NUM_PREDICT_HEAVY = 512
NUM_PREDICT_LIGHT = 256
NUM_CTX = int(os.environ.get("LOCAL_OLLAMA_NUM_CTX", "2048"))
OLLAMA_TIMEOUT = int(os.environ.get("LOCAL_OLLAMA_TIMEOUT", "600"))


def _mock_enabled() -> bool:
    return os.environ.get("LOCAL_MOCK_LLM", "").lower() in ("1", "true", "yes")


def _llm_provider() -> str:
    """gemini (default) | openrouter | ollama (disabled)."""
    p = os.environ.get("LOCAL_LLM_PROVIDER", "gemini").lower().strip()
    if p in ("openrouter",):
        return "openrouter"
    # Strict user directive: Gemini is default and primary
    return "gemini"


def _mock_response(fsm_state: str, tier: str) -> dict[str, Any]:
    if fsm_state == "peer_review" or fsm_state == "json_repair":
        return {"approved": True, "reasons": ["mock: params within bounds"]}
    return {
        "hypothesis": "mock: lower lr may reduce val_loss",
        "params": {"lr": 0.01, "hidden_dim": 32, "steps": 50},
        "rationale": "mock proposal",
    }


def generate_fsm_json(
    prompt: str,
    system_instruction: str,
    tier: str = "auto",
    fsm_state: str = "propose",
    max_retries: int = 2,
    force_heavy: bool = False,
) -> dict[str, Any]:
    """
    Communicates with local Ollama via qwen35custom tier routing.
    tier: "auto" (difficulty-based), "heavy", or "light".
    Set LOCAL_MOCK_LLM=1 to run without LLM (tests / CI).
    Set LOCAL_LLM_PROVIDER=openrouter + OPENROUTER_API_KEY for cloud (no GPU).
    """
    from local.llm.secrets import bootstrap_env

    bootstrap_env()

    if tier == "auto":
        decision = score_difficulty(
            fsm_state, prompt, system_instruction, force_heavy=force_heavy
        )
        tier = decision.tier
        print(
            f"[qwen35custom] {fsm_state} -> {decision.tier} "
            f"({decision.model}) score={decision.score:.2f} {decision.reason}"
        )
    else:
        decision = None

    if _mock_enabled():
        print("[qwen35custom] MOCK MODE — no LLM (unset LOCAL_MOCK_LLM)")
        return _mock_response(fsm_state, tier)

    provider = _llm_provider()
    num_tok = NUM_PREDICT_LIGHT if tier == "light" else NUM_PREDICT_HEAVY

    if provider == "openrouter":
        from local.llm.openrouter_client import generate_json as cloud_generate
        from local.llm.openrouter_client import resolve_openrouter_model

        out = cloud_generate(
            prompt,
            system_instruction,
            model=resolve_openrouter_model(tier, fsm_state),
            tier=tier,
            fsm_state=fsm_state,
            max_tokens=num_tok,
        )
        if out.get("status") != "error":
            return out
        print(f"[OpenRouter] error, trying Gemini: {out.get('reason', '')[:100]}")

    if provider == "gemini":
        from local.llm.gemini_client import generate_json as gem_generate

        gem_model = decision.model if decision else qwen35custom.resolve_model(fsm_state, tier=tier)
        out = gem_generate(
            prompt,
            system_instruction,
            model=gem_model,
            tier=tier,
            fsm_state=fsm_state,
            max_tokens=num_tok,
        )
        return out

    model = (
        decision.model
        if decision
        else qwen35custom.resolve_model(fsm_state, tier=tier)
    )
    num_predict = NUM_PREDICT_LIGHT if tier == "light" else NUM_PREDICT_HEAVY

    options = {
        "temperature": 0.0,
        "num_predict": num_predict,
        "num_ctx": NUM_CTX,
    }
    if os.environ.get("LOCAL_OLLAMA_NUM_GPU"):
        options["num_gpu"] = int(os.environ["LOCAL_OLLAMA_NUM_GPU"])

    payload = {
        "model": model,
        "prompt": prompt,
        "system": system_instruction,
        "format": "json",
        "stream": False,
        "options": options,
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            response.raise_for_status()
            result_text = response.json().get("response", "")
            return json.loads(result_text)
        except json.JSONDecodeError:
            print(f"[Warning] JSON parsing failed on attempt {attempt + 1}. Retrying...")
        except Exception as e:
            print(f"[Error] API communication failed: {e}")
            break

    print("[Error] Max retries reached. Triggering deterministic fallback payload.")
    return {
        "status": "error",
        "decision": "reject",
        "reason": "LLM failed to produce valid JSON state.",
    }


def unload_model_from_vram() -> None:
    """Purge gateway and tier backends from VRAM (keep_alive=0)."""
    if _mock_enabled() or _llm_provider() in ("openrouter", "gemini"):
        print("[Memory Management] cloud LLM — skip local VRAM unload")
        return

    print(f"[Memory Management] Unloading {GATEWAY_MODEL} (all tiers) from VRAM...")
    for model in (GATEWAY_MODEL, TIER_HEAVY, TIER_LIGHT):
        try:
            requests.post(
                OLLAMA_API_URL,
                json={"model": model, "keep_alive": 0},
                timeout=30,
            )
        except Exception as e:
            print(f"[Warning] unload {model}: {e}")
    print("[Memory Management] VRAM cleared successfully.")
