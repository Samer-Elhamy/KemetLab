#!/usr/bin/env python3
"""CLI helper for diagnose_runtime.ps1."""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from local.llm.runtime_health import check_pytorch_cuda, mock_mode_enabled, run_runtime_health

print("LOCAL_MOCK_LLM =", repr(__import__("os").environ.get("LOCAL_MOCK_LLM")))
pt = check_pytorch_cuda()
print("torch cuda_available:", pt.get("cuda_available"), pt.get("device_name") or "")
print()
r = run_runtime_health(quick_probe=False)
line = r["summary_ar"]
try:
    print(line)
except UnicodeEncodeError:
    print(line.encode("ascii", errors="replace").decode())
print()
print(
    json.dumps(
        {
            k: r[k]
            for k in (
                "mock_mode",
                "ready_for_real_run",
                "missing_models",
                "ollama",
                "ollama_ps",
                "generate_probe",
            )
        },
        indent=2,
        ensure_ascii=False,
    )
)
