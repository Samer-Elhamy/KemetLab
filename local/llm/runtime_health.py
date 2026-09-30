"""Check Ollama, mock mode, PyTorch CUDA — before / during local runs."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from local.llm import qwen35custom

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
HEALTH_FILE = "runtime_health.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mock_mode_enabled() -> bool:
    return os.environ.get("LOCAL_MOCK_LLM", "").lower() in ("1", "true", "yes")


def check_pytorch_cuda() -> dict[str, Any]:
    try:
        import torch

        cuda_ok = torch.cuda.is_available()
        name = torch.cuda.get_device_name(0) if cuda_ok else None
        return {
            "installed": True,
            "cuda_available": cuda_ok,
            "device_name": name,
            "note_ar": (
                "PyTorch يرى GPU — train.py يمكنه استخدام CUDA"
                if cuda_ok
                else "PyTorch على CPU فقط — ثبّت torch+cuda أو درّب على CPU"
            ),
        }
    except ImportError:
        return {
            "installed": False,
            "cuda_available": False,
            "device_name": None,
            "note_ar": "PyTorch غير مثبت — train.py يستخدم محاكاة numpy (CPU)",
        }


def check_gemini_proxy_reachable() -> dict[str, Any]:
    try:
        r = requests.get("http://127.0.0.1:8317/v1/models", headers={"Authorization": "Bearer 123456"}, timeout=5)
        if r.ok:
            models = [m.get("id", "") for m in r.json().get("data", [])]
            return {"reachable": True, "models": models, "error": None}
        return {"reachable": False, "models": [], "error": f"HTTP {r.status_code}"}
    except Exception as exc:
        return {"reachable": False, "models": [], "error": str(exc)}

def check_ollama_reachable() -> dict[str, Any]:
    cfg = qwen35custom.load_routing()
    if cfg.get("gateway") == "gemini" or cfg.get("provider") == "gemini":
        return check_gemini_proxy_reachable()
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
        return {"reachable": True, "models": models, "error": None}
    except Exception as exc:
        return {"reachable": False, "models": [], "error": str(exc)}


def check_ollama_loaded() -> dict[str, Any]:
    """Models currently in memory (VRAM) — visible in Task Manager under ollama.exe."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5)
        r.raise_for_status()
        loaded = r.json().get("models", [])
        vram = sum(int(m.get("size_vram") or 0) for m in loaded)
        return {
            "loaded": loaded,
            "count": len(loaded),
            "vram_bytes": vram,
            "using_vram": vram > 0,
        }
    except Exception as exc:
        return {"loaded": [], "count": 0, "vram_bytes": 0, "using_vram": False, "error": str(exc)}


def required_models() -> list[str]:
    cfg = qwen35custom.load_routing()
    tiers = cfg.get("tiers", {})
    if cfg.get("gateway") == "gemini" or cfg.get("provider") == "gemini":
        return list(dict.fromkeys([
            tiers.get("heavy", "gemini-3.8-flash-high"),
            tiers.get("light", "gemini-3.8-flash-lite")
        ]))
    return list(
        dict.fromkeys(
            [
                tiers.get("heavy", "qwen3.5-9b-gguf:ud-q4_k_xl"),
                tiers.get("light", "qwen3.5:0.8b-gguf"),
                cfg.get("gateway", "qwen35custom"),
            ]
        )
    )


def _model_present(name: str, installed: list[str]) -> bool:
    cfg = qwen35custom.load_routing()
    if cfg.get("gateway") == "gemini" or cfg.get("provider") == "gemini":
        if "3.8-flash-lite" in name:
            # Map logical gemini-3.8-flash-lite to upstream flash-lite in proxy
            return any("flash-lite" in m for m in installed)
        return any(name.split(":")[0] in m for m in installed)
    base = name.split(":")[0]
    for m in installed:
        if m == name or m.startswith(name + ":") or m.split(":")[0] == base:
            return True
    return False


def probe_ollama_generate(model: str, timeout: int = 60) -> dict[str, Any]:
    if mock_mode_enabled():
        return {"ok": True, "skipped": True, "reason": "LOCAL_MOCK_LLM=1"}
    cfg = qwen35custom.load_routing()
    if cfg.get("gateway") == "gemini" or cfg.get("provider") == "gemini":
        try:
            r = requests.post(
                "http://127.0.0.1:8317/v1/chat/completions",
                headers={"Authorization": "Bearer 123456", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 10
                },
                timeout=timeout
            )
            if r.ok:
                return {"ok": True, "model": model, "sample": "gemini_proxy_ok"}
            return {"ok": False, "model": model, "error": f"HTTP {r.status_code}: {r.text[:100]}"}
        except Exception as exc:
            return {"ok": False, "model": model, "error": str(exc)}
    try:
        payload = {
            "model": model,
            "prompt": '{"ok":true}',
            "stream": False,
            "format": "json",
            "options": {"num_predict": 8, "temperature": 0},
        }
        r = requests.post(f"{OLLAMA_BASE}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        text = r.json().get("response", "")
        return {"ok": True, "model": model, "sample": text[:80]}
    except Exception as exc:
        return {"ok": False, "model": model, "error": str(exc)}


def run_runtime_health(*, quick_probe: bool = False) -> dict[str, Any]:
    """
    Full diagnostic snapshot.
    quick_probe=False skips live generate (faster for dashboard poll).
    """
    mock = mock_mode_enabled()
    required = required_models()
    tags = check_ollama_reachable()
    ps = check_ollama_loaded()
    torch_info = check_pytorch_cuda()

    missing = []
    if tags.get("reachable"):
        installed = tags.get("models") or []
        for m in required:
            if not _model_present(m, installed):
                missing.append(m)

    probe = None
    if not mock and quick_probe is False and tags.get("reachable") and not missing:
        heavy = qwen35custom.resolve_model("propose", tier="heavy")
        probe = probe_ollama_generate(heavy, timeout=90)

    ready_for_real_run = (
        not mock
        and tags.get("reachable")
        and len(missing) == 0
        and (probe is None or probe.get("ok"))
    )

    return {
        "ts": _now(),
        "mock_mode": mock,
        "ollama_base": OLLAMA_BASE,
        "ollama": tags,
        "ollama_ps": ps,
        "pytorch": torch_info,
        "required_models": required,
        "missing_models": missing,
        "generate_probe": probe,
        "ready_for_real_run": ready_for_real_run,
        "summary_ar": _summary_ar(mock, tags, missing, ps, torch_info, probe),
    }


def _summary_ar(
    mock: bool,
    tags: dict,
    missing: list,
    ps: dict,
    torch_info: dict,
    probe: dict | None,
) -> str:
    if mock:
        return (
            "⚠️ وضع MOCK مفعّل (LOCAL_MOCK_LLM=1) — لا يُستدعى Ollama ولا يظهر GPU لـ qwen. "
            "أزل المتغير وأعد تشغيل اللوحة للتشغيل الحقيقي."
        )
    if not tags.get("reachable"):
        return (
            f"❌ Ollama غير متصل على {OLLAMA_BASE} — شغّل: ollama serve "
            "ثم ollama pull للموديلات."
        )
    if missing:
        gw = qwen35custom.gateway_name()
        if _model_present(gw, tags.get("models") or []):
            return (
                f"⚠️ الموديلات الخلفية ناقصة: {', '.join(missing)} — "
                f"لكن `{gw}` موجود. نفّذ ollama pull للـ heavy/light أو عدّل local/config/routing.yaml"
            )
        return f"❌ موديلات ناقصة: {', '.join(missing)} — نفّذ ollama pull لكل واحد."
    if probe and not probe.get("ok"):
        return f"❌ فشل اختبار التوليد: {probe.get('error', '')[:120]}"
    vram = ps.get("vram_bytes") or 0
    if vram > 0:
        return (
            f"✅ Ollama جاهز — {ps.get('count', 0)} موديل في الذاكرة "
            f"(~{vram // (1024*1024)} MB VRAM). ابحث عن ollama.exe في Task Manager → GPU."
        )
    return (
        "✅ Ollama متصل والموديلات موجودة. أثناء Propose سيُحمَّل الموديل — "
        "راقب ollama.exe على تبويب GPU (ليس python.exe بالضرورة)."
    )


def save_health_report(focus_root: Path | None, report: dict[str, Any]) -> Path | None:
    if not focus_root:
        return None
    path = Path(focus_root).resolve() / "logs" / HEALTH_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_health_report(focus_root: Path) -> dict[str, Any] | None:
    path = Path(focus_root).resolve() / "logs" / HEALTH_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def run_ollama_ps_cli() -> str:
    try:
        out = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return (out.stdout or "") + (out.stderr or "")
    except FileNotFoundError:
        return "ollama CLI not in PATH"
    except Exception as exc:
        return str(exc)
