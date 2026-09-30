"""Google Gemini Client with native AI Studio API & Local OpenAI-compatible CPA Proxy support."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from local.llm.secrets import bootstrap_env

DEFAULT_PROXY_BASE = "http://127.0.0.1:8317/v1"
DEFAULT_PROXY_KEY = "123456"
TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "120"))


def _api_key() -> str | None:
    bootstrap_env()
    return (
        os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or ""
    ).strip() or None


def _proxy_base_url() -> str:
    return os.environ.get("GEMINI_PROXY_BASE_URL", DEFAULT_PROXY_BASE).rstrip("/")


def _proxy_api_key() -> str:
    return os.environ.get("GEMINI_PROXY_API_KEY", DEFAULT_PROXY_KEY)


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


def generate_json(
    prompt: str,
    system_instruction: str,
    *,
    model: str = "gemini-3.8-flash-high",
    tier: str = "heavy",
    fsm_state: str = "propose",
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Execute JSON generation via Gemini model, trying local proxy first or direct API key."""
    # 1. Try local OpenAI-compatible Gemini proxy (CPA-GUI at 127.0.0.1:8317)
    proxy_url = f"{_proxy_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_proxy_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    # Multi-tier Smart Allocation & Fallback for Heavy Thinking:
    # When tier is heavy, randomly distribute across the 3 top diverse models to ensure ideological diversity:
    # 1. gemini-3.8-flash-high (Google Frontier)
    # 2. claude-opus-4-6-thinking (Anthropic Deep Reasoning)
    # 3. claude-sonnet-4-6 (Anthropic Code & Architecture)
    HEAVY_TITANS = ["gemini-3.8-flash-high", "claude-opus-4-6-thinking", "claude-sonnet-4-6"]

    import random
    if tier == "heavy" and (model in HEAVY_TITANS or model == "auto" or "gemini" in model):
        shuffled_titans = HEAVY_TITANS.copy()
        random.shuffle(shuffled_titans)
        candidate_models = shuffled_titans + ["gemini-3.8-flash-lite"]
    else:
        candidate_models = [model]
        candidate_models.extend(["gemini-3.8-flash-high", "claude-opus-4-6-thinking", "claude-sonnet-4-6", "gemini-3.8-flash-lite"])
    candidate_models = list(dict.fromkeys(candidate_models))

    for cand_model in candidate_models:
        payload["model"] = cand_model
        try:
            resp = requests.post(proxy_url, json=payload, headers=headers, timeout=TIMEOUT)
            if resp.ok:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                res = _extract_json(content)
                if res and res.get("status") != "error":
                    return res
            print(f"[Smart Fallback] Model {cand_model} failed (HTTP {resp.status_code}). Switching to next candidate...")
        except Exception as proxy_err:
            print(f"[Smart Fallback] Connection error with {cand_model}: {proxy_err}. Trying next...")
            continue

    # 2. Fallback to direct GenerativeLanguage API if API Key is configured
    key = _api_key()
    if key:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        try:
            resp = requests.post(url, json=body, timeout=TIMEOUT)
            if resp.ok:
                data = resp.json()
                parts = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])
                )
                text = parts[0].get("text", "") if parts else ""
                return _extract_json(text)
            return {"status": "error", "reason": f"Gemini Direct {resp.status_code}: {resp.text[:200]}"}
        except Exception as exc:
            return {"status": "error", "reason": f"Gemini Direct error: {exc}"}

    return {
        "status": "error",
        "reason": "Failed to communicate with local Gemini proxy (127.0.0.1:8317) and no GEMINI_API_KEY present.",
    }
