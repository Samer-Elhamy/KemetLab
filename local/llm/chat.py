"""Natural-language chat via qwen35custom (non-JSON)."""

from __future__ import annotations

import os
from typing import Generator

import requests

from local.llm import qwen35custom
from local.llm.difficulty import score_difficulty

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
NUM_CTX = 4096
NUM_PREDICT_CHAT = 768


def _mock_enabled() -> bool:
    return os.environ.get("LOCAL_MOCK_LLM", "").lower() in ("1", "true", "yes")


def generate_chat(
    user_message: str,
    system_instruction: str,
    *,
    tier: str = "auto",
) -> str:
    """Single-shot chat completion."""
    if _mock_enabled():
        return (
            "**وضع تجريبي (Mock)**\n\n"
            "بناءً على السجلات المحلية: آخر champion محسّن، وتجارب KEEP/DISCARD مسجّلة. "
            "شغّل Ollama لإجابات حقيقية من qwen35custom.\n\n"
            f"سؤالك: {user_message[:200]}"
        )

    if tier == "auto":
        decision = score_difficulty("research_chat", user_message, system_instruction)
        tier = decision.tier
        model = decision.model
    else:
        model = qwen35custom.resolve_model("research_chat", tier=tier)

    num_predict = 384 if tier == "light" else NUM_PREDICT_CHAT
    payload = {
        "model": model,
        "prompt": user_message,
        "system": system_instruction,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": num_predict,
            "num_ctx": NUM_CTX,
        },
    }
    try:
        resp = requests.post(OLLAMA_API_URL, json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json().get("response", "").strip() or "(لا توجد إجابة من النموذج)"
    except Exception as e:
        return f"**خطأ Ollama:** {e}\n\nتأكد أن `ollama serve` يعمل والموديلات مُحمّلة."


def stream_chat(
    user_message: str,
    system_instruction: str,
    *,
    tier: str = "auto",
) -> Generator[str, None, None]:
    """Stream tokens for Cursor-like typing effect."""
    if _mock_enabled():
        yield generate_chat(user_message, system_instruction, tier=tier)
        return

    if tier == "auto":
        decision = score_difficulty("research_chat", user_message, system_instruction)
        tier = decision.tier
        model = decision.model
    else:
        model = qwen35custom.resolve_model("research_chat", tier=tier)

    payload = {
        "model": model,
        "prompt": user_message,
        "system": system_instruction,
        "stream": True,
        "options": {
            "temperature": 0.3,
            "num_predict": NUM_PREDICT_CHAT if tier == "heavy" else 384,
            "num_ctx": NUM_CTX,
        },
    }
    try:
        with requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=180) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                import json

                chunk = json.loads(line)
                if "response" in chunk:
                    yield chunk["response"]
    except Exception as e:
        yield f"**خطأ:** {e}"
