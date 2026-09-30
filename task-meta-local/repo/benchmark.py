#!/usr/bin/env python3
"""Benchmark resource usage of the experiments repo (Ollama dual-tier + smoke cycle timing)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


def _target_repo() -> Path:
    p = os.environ.get("AUTOSCIENTISTS_TARGET_REPO", "")
    if not p:
        raise RuntimeError("Set AUTOSCIENTISTS_TARGET_REPO to experiments repo path")
    return Path(p).resolve()


def _ollama_ping(model: str, timeout: int = 120) -> tuple[bool, float, str]:
    import requests

    url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
    t0 = time.perf_counter()
    try:
        r = requests.post(
            url,
            json={
                "model": model,
                "prompt": '{"ok":true}',
                "format": "json",
                "stream": False,
                "options": {"num_predict": 16, "temperature": 0},
            },
            timeout=timeout,
        )
        elapsed = time.perf_counter() - t0
        if r.status_code != 200:
            return False, elapsed, f"HTTP {r.status_code}"
        return True, elapsed, "ok"
    except Exception as e:
        return False, time.perf_counter() - t0, str(e)[:120]


def _resolve_models(repo: Path) -> tuple[str, str]:
    sys.path.insert(0, str(repo))
    try:
        from local.llm import qwen35custom

        heavy = qwen35custom.resolve_model("propose", tier="heavy")
        light = qwen35custom.resolve_model("json_repair", tier="light")
        return heavy, light
    finally:
        if str(repo) in sys.path:
            sys.path.remove(str(repo))


def _ram_mb() -> float:
    if psutil:
        return psutil.virtual_memory().percent
    return 0.0


def main() -> None:
    repo = _target_repo()
    heavy, light = _resolve_models(repo)

    skip_ollama = os.environ.get("META_BENCHMARK_SKIP_OLLAMA", "").lower() in ("1", "true", "yes")
    local_only = os.environ.get("LOCAL_ONLY", "").lower() in ("1", "true", "yes")

    metrics: dict = {
        "heavy_model": heavy,
        "light_model": light,
        "ram_percent": _ram_mb(),
        "local_only": local_only,
    }

    if skip_ollama or local_only:
        metrics["heavy_ok"] = False
        metrics["light_ok"] = False
        metrics["heavy_sec"] = 0.0
        metrics["light_sec"] = 0.0
        metrics["note"] = "local-only offline benchmark (no Ollama penalty)"
    else:
        h_ok, h_sec, h_msg = _ollama_ping(heavy)
        l_ok, l_sec, l_msg = _ollama_ping(light)
        metrics.update(
            {
                "heavy_ok": h_ok,
                "heavy_sec": round(h_sec, 3),
                "heavy_msg": h_msg,
                "light_ok": l_ok,
                "light_sec": round(l_sec, 3),
                "light_msg": l_msg,
            }
        )

    # Smoke train timing (PyTorch path in experiments venv if available)
    train = repo / "task-smoke-local" / "repo" / "train.py"
    train_sec = 0.0
    if train.exists():
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(train)],
            cwd=str(train.parent),
            capture_output=True,
            text=True,
            timeout=180,
            env={
                **os.environ,
                "SMOKE_LR": "0.01",
                "SMOKE_HIDDEN": "32",
                "SMOKE_STEPS": "30",
            },
        )
        train_sec = time.perf_counter() - t0
        metrics["train_sec"] = round(train_sec, 3)
        metrics["train_ok"] = proc.returncode == 0

    # Composite score (lower is better)
    fail_penalty = 0.0
    if not skip_ollama and not local_only:
        if not metrics.get("heavy_ok"):
            fail_penalty += 200.0
        if not metrics.get("light_ok"):
            fail_penalty += 100.0
    score = (
        fail_penalty
        + float(metrics.get("heavy_sec", 0)) * 2.0
        + float(metrics.get("light_sec", 0)) * 0.5
        + train_sec * 0.1
        + metrics["ram_percent"] * 0.3
    )
    score = round(score, 4)

    out = {
        "resource_score": score,
        "exp_id": os.environ.get("META_EXP_ID", "meta_bench"),
        "params": {"heavy": heavy, "light": light},
        "metrics": metrics,
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
