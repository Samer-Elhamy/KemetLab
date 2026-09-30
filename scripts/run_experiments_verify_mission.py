#!/usr/bin/env python3
"""Run N local-only FSM cycles using experiments repo code (PYTHONPATH)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_EXP = Path(os.environ.get("EXPERIMENTS_REPO", r"C:\Users\Samer\AutoScientists-Local-Experiments"))
_REPO = Path(__file__).resolve().parents[1]
for p in (_EXP, _REPO):
    ps = str(p)
    if ps not in sys.path:
        sys.path.insert(0, ps)


def _load_local_only_env() -> None:
    env_file = _EXP / "local" / "config" / "local_only.env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
    os.environ.pop("LOCAL_MOCK_LLM", None)
    os.environ.pop("OPENROUTER_API_KEY", None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--focus-root", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=3)
    args = parser.parse_args()

    _load_local_only_env()
    os.environ["LOCAL_ONLY"] = "1"
    os.environ["LOCAL_LLM_PROVIDER"] = "ollama"

    # Import from experiments repo (first on PYTHONPATH)
    import local.llm.ollama_client as oc

    provider_fn = getattr(oc, "_llm_provider", None)
    if provider_fn and provider_fn() != "ollama":
        print("FAIL: not local-only provider", provider_fn())
        return 1

    from local.orchestrator.runner import run_iteration

    focus = args.focus_root.resolve()
    results = []
    for i in range(args.cycles):
        cycle = i + 1
        print(f"\n=== VERIFY CYCLE {cycle} ===")
        out = run_iteration(focus, cycle=cycle)
        results.append(out)
        print(out)
        if out.get("state") == "error" or out.get("outcome") == "ERROR":
            print("FAIL: cycle error")
            return 1

    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "cycles": args.cycles,
        "local_only": True,
        "experiments_repo": str(_EXP),
        "results": results,
        "ok": True,
    }
    out_path = focus / "logs" / "verify_mission_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (_EXP / "VERIFY_MISSION_OK.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSUCCESS: {args.cycles} local cycles — report {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
