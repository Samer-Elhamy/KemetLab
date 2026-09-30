#!/usr/bin/env python3
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from local.llm.openrouter_client import generate_json
from local.llm.secrets import bootstrap_env

bootstrap_env()
models = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-2-9b-it:free",
    "qwen/qwen-2.5-7b-instruct:free",
    "qwen/qwen3-coder:free",
]
prompt = (
    "Return JSON with keys: hypothesis (string), params (object with lr, hidden_dim, steps), "
    "rationale (string). Minimize val_loss."
)
for m in models:
    os.environ["OPENROUTER_MODEL_HEAVY"] = m
    r = generate_json(prompt, "JSON only.", fsm_state="propose", model=m)
    ok = bool(r.get("params") or r.get("hypothesis"))
    print(m, "OK" if ok else "FAIL", r.get("reason", r.get("status", ""))[:100])
    if ok:
        print("sample params", r.get("params"))
        sys.exit(0)
sys.exit(1)
