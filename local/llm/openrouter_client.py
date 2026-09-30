"""OpenRouter chat completions (free :free models, no local GPU)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from local.llm.secrets import openrouter_api_key

OPENROUTER_URL = os.environ.get(
    "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
)
DEFAULT_HEAVY = os.environ.get(
    "OPENROUTER_MODEL_HEAVY", "meta-llama/llama-3.3-70b-instruct:free"
)
DEFAULT_LIGHT = os.environ.get(
    "OPENROUTER_MODEL_LIGHT", "meta-llama/llama-3.3-70b-instruct:free"
)
DEFAULT_FREE = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
TIMEOUT = int(os.environ.get("OPENROUTER_TIMEOUT", "120"))
FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "OPENROUTER_FALLBACK_MODELS",
        "openrouter/free,qwen/qwen3-coder:free,meta-llama/llama-3.3-70b-instruct:free,"
        "deepseek/deepseek-r1-distill-llama-70b:free,mistralai/mistral-7b-instruct:free",
    ).split(",")
    if m.strip()
]


def resolve_openrouter_model(tier: str, fsm_state: str) -> str:
    if tier == "light":
        return os.environ.get("OPENROUTER_MODEL_LIGHT") or DEFAULT_LIGHT
    if tier == "heavy":
        return os.environ.get("OPENROUTER_MODEL_HEAVY") or DEFAULT_HEAVY
    return os.environ.get("OPENROUTER_MODEL") or DEFAULT_FREE


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise json.JSONDecodeError("empty", text, 0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise json.JSONDecodeError("no json object", text, 0)


def _generate_json_once(
    prompt: str,
    system_instruction: str,
    *,
    model: str,
    fsm_state: str,
    max_tokens: int,
    api_key: str,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("OPENROUTER_HTTP_REFERER", "http://localhost:8501"),
        "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "AutoScientists-Local"),
    }
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    system_instruction
                    + "\n\nRespond with a single valid JSON object only, no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if model != "openrouter/free":
        body["response_format"] = {"type": "json_object"}

    print(f"[OpenRouter] {fsm_state} model={model}", flush=True)
    try:
        import time

        resp = None
        for attempt in range(4):
            resp = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=TIMEOUT)
            if resp.status_code != 429:
                break
            wait = 25
            try:
                meta = resp.json().get("error", {}).get("metadata", {})
                wait = int(meta.get("retry_after_seconds") or wait)
            except (ValueError, TypeError, AttributeError):
                pass
            print(f"[OpenRouter] 429 rate limit — wait {wait}s (attempt {attempt + 1})", flush=True)
            time.sleep(min(wait, 60))
        if resp is None:
            return {"status": "error", "reason": "OpenRouter: no response"}
        if not resp.ok:
            err = resp.text[:400]
            print(f"[OpenRouter] HTTP {resp.status_code}: {err}", flush=True)
            return {"status": "error", "reason": f"OpenRouter {resp.status_code}: {err[:200]}"}
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        if not str(content).strip():
            return {"status": "error", "reason": "empty response from model"}
        return _extract_json(content)
    except json.JSONDecodeError as exc:
        return {"status": "error", "reason": f"invalid JSON from model: {exc}"}
    except requests.RequestException as exc:
        return {"status": "error", "reason": str(exc)}


def generate_json(
    prompt: str,
    system_instruction: str,
    *,
    model: str | None = None,
    tier: str = "heavy",
    fsm_state: str = "propose",
    max_tokens: int = 512,
) -> dict[str, Any]:
    api_key = openrouter_api_key()
    if not api_key:
        return {
            "status": "error",
            "reason": "OPENROUTER_API_KEY missing — add to .env or ~/.hermes/.env",
        }

    primary = model or resolve_openrouter_model(tier, fsm_state)
    models = [primary] + [m for m in FALLBACK_MODELS if m != primary]

    last_err = ""
    for m in models:
        out = _generate_json_once(
            prompt,
            system_instruction,
            model=m,
            fsm_state=fsm_state,
            max_tokens=max_tokens,
            api_key=api_key,
        )
        if out.get("status") != "error":
            return out
        last_err = out.get("reason", "")
        if "429" in last_err:
            import time

            time.sleep(22)
    return {"status": "error", "reason": last_err or "all OpenRouter models failed"}
