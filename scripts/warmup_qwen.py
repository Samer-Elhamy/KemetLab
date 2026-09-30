#!/usr/bin/env python3
"""Warm up Ollama qwen35custom and verify JSON generation."""
import json
import os
import sys
import time
from pathlib import Path

import requests

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
os.environ.pop("LOCAL_MOCK_LLM", None)

from local.llm import qwen35custom

qwen35custom._ROUTING_CACHE = None
model = os.environ.get("LOCAL_OLLAMA_HEAVY") or qwen35custom.resolve_model(
    "propose", tier="heavy"
)
print(f"model={model}", flush=True)

opts = {
    "num_predict": 64,
    "num_ctx": int(os.environ.get("LOCAL_OLLAMA_NUM_CTX", "1024")),
    "temperature": 0,
}
if os.environ.get("LOCAL_OLLAMA_NUM_GPU"):
    opts["num_gpu"] = int(os.environ["LOCAL_OLLAMA_NUM_GPU"])

t0 = time.time()
r = requests.post(
    "http://127.0.0.1:11434/api/generate",
    json={
        "model": model,
        "prompt": 'Return JSON only: {"approved": true, "reasons": ["warmup"]}',
        "stream": False,
        "format": "json",
        "options": opts,
    },
    timeout=int(os.environ.get("LOCAL_OLLAMA_TIMEOUT", "600")),
)
print(f"status={r.status_code} elapsed={time.time()-t0:.1f}s", flush=True)
if not r.ok:
    print(r.text[:800], flush=True)
    sys.exit(1)
text = r.json().get("response", "")
print("response:", text[:200], flush=True)
obj = json.loads(text)
print("ok:", obj, flush=True)
