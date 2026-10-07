"""
KemetLab Embedded CPA (EasyCLIProxy) Native Service Manager.
Provides internal lifecycle management, Antigravity Google OAuth login,
multi-account pool tracking, live quota/cooldown metrics, and server control.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

# Default CPA management constants
CPA_HOST = "127.0.0.1"
CPA_PORT = 8317
CPA_BASE_URL = f"http://{CPA_HOST}:{CPA_PORT}"
MANAGEMENT_KEY = "wui-Aa9_m9xNVo9NkNAk0P6cihWm3Jcb25WLObPv-PiQ53N143o"
PROXY_API_KEY = "123456"

# Candidate paths for cli-proxy-api binary
SEARCH_PATHS = [
    Path(r"C:\Users\Samer\AutoScientists-Local\tools\cpa\cpa-core\cli-proxy-api.exe"),
    Path(r"C:\Users\Samer\Downloads\EasyCLIProxyAPI-v0.2.99-Windows-amd64\EasyCLIProxyAPI-v0.2.99-Windows-amd64\cpa-core\cli-proxy-api.exe"),
]

def find_cpa_binary() -> Path | None:
    for p in SEARCH_PATHS:
        if p.exists():
            return p
    # Check relative to this repo
    repo_cpa = Path(__file__).resolve().parent.parent.parent / "tools" / "cpa" / "cpa-core" / "cli-proxy-api.exe"
    if repo_cpa.exists():
        return repo_cpa
    return None

def find_cpa_config() -> Path | None:
    bin_path = find_cpa_binary()
    if bin_path:
        cfg = bin_path.parent / "config.yaml"
        if cfg.exists():
            return cfg
    return None

def find_oauth_dir() -> Path:
    bin_path = find_cpa_binary()
    if bin_path:
        d = bin_path.parent.parent / "oauth"
        if d.exists():
            return d
        d2 = bin_path.parent / "oauth"
        if d2.exists():
            return d2
    # fallback to local repo tools
    fallback = Path(r"C:\Users\Samer\AutoScientists-Local\tools\cpa\oauth")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

def _make_management_request(endpoint: str, method: str = "GET", data: dict | None = None) -> Any:
    url = f"{CPA_BASE_URL}{endpoint}"
    headers = {
        "X-Management-Key": MANAGEMENT_KEY,
        "Accept": "application/json",
    }
    payload = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))

def is_cpa_running() -> bool:
    try:
        url = f"{CPA_BASE_URL}/v1/models"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {PROXY_API_KEY}"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False

def start_cpa_server() -> bool:
    if is_cpa_running():
        return True

    bin_path = find_cpa_binary()
    cfg_path = find_cpa_config()
    if not bin_path or not cfg_path:
        return False

    cmd = [str(bin_path), "-config", str(cfg_path)]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(cmd, cwd=str(bin_path.parent), creationflags=flags)
    # wait up to 6 seconds
    for _ in range(12):
        time.sleep(0.5)
        if is_cpa_running():
            return True
    return False

def stop_cpa_server() -> bool:
    if not is_cpa_running():
        return True
    try:
        # kill process listening on 8317 on Windows
        cmd = 'powershell -Command "Get-NetTCPConnection -LocalPort 8317 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"'
        subprocess.run(cmd, shell=True, timeout=5)
        time.sleep(1)
        return not is_cpa_running()
    except Exception:
        return False

def get_cpa_status() -> dict[str, Any]:
    running = is_cpa_running()
    models = []
    if running:
        try:
            url = f"{CPA_BASE_URL}/v1/models"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {PROXY_API_KEY}"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("id") for m in data.get("data", [])]
        except Exception:
            pass

    return {
        "online": running,
        "port": CPA_PORT,
        "base_url": CPA_BASE_URL,
        "models_count": len(models),
        "models": models,
        "binary_present": find_cpa_binary() is not None,
    }

def get_accounts() -> list[dict[str, Any]]:
    """Retrieve all linked Antigravity OAuth accounts with live quota and cooldown data."""
    results = []
    # Try Management API first
    if is_cpa_running():
        try:
            data = _make_management_request("/v8/management/credentials")
            files = data.get("files", []) if isinstance(data, dict) else []
            for f in files:
                cooldowns = f.get("cooldowns", []) or []
                cooldown_info = []
                for cd in cooldowns:
                    cooldown_info.append({
                        "model": cd.get("model_key", "unknown"),
                        "remaining_seconds": cd.get("remaining_seconds", 0),
                        "status_code": cd.get("http_status", 429),
                        "reason": cd.get("reason", "cooldown"),
                    })

                results.append({
                    "id": f.get("id", f.get("name")),
                    "name": f.get("name"),
                    "email": f.get("email") or f.get("account"),
                    "provider": f.get("provider", "antigravity"),
                    "status": "disabled" if f.get("disabled") else ("cooldown" if cooldown_info else "active"),
                    "disabled": bool(f.get("disabled")),
                    "success_count": f.get("success", 0),
                    "failed_count": f.get("failed", 0),
                    "cooldowns": cooldown_info,
                    "last_refresh": f.get("last_refresh", ""),
                    "project_id": f.get("project_id", "aicode-consumers"),
                })
            if results:
                return results
        except Exception:
            pass

    # Fallback to local files if proxy offline or management API failed
    oauth_dir = find_oauth_dir()
    if oauth_dir.exists():
        for json_file in oauth_dir.glob("antigravity-*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as fp:
                    d = json.load(fp)
                results.append({
                    "id": json_file.name,
                    "name": json_file.name,
                    "email": d.get("email", json_file.stem.replace("antigravity-", "")),
                    "provider": "antigravity",
                    "status": "disabled" if d.get("disabled") else "active",
                    "disabled": bool(d.get("disabled")),
                    "success_count": 0,
                    "failed_count": 0,
                    "cooldowns": [],
                    "last_refresh": d.get("expired", ""),
                    "project_id": d.get("project_id", "aicode-consumers"),
                })
            except Exception:
                continue

    return results

def start_antigravity_oauth() -> dict[str, Any]:
    """Trigger Google OAuth login flow for Antigravity and open browser."""
    if not is_cpa_running():
        started = start_cpa_server()
        if not started:
            return {"status": "error", "message": "فشل تشغيل سيرفر CPA الداخلي."}

    try:
        data = _make_management_request("/v8/management/oauth/auth-url?provider=antigravity")
        auth_url = data.get("url")
        if auth_url:
            webbrowser.open(auth_url)
            return {
                "status": "success",
                "message": "تم فتح صفحة تسجيل الدخول في المتصفح بنجاح! يرجى اختيار حساب Google والموافقة.",
                "auth_url": auth_url,
            }
        return {"status": "error", "message": "لم يتم العثور على رابط المصادقة من السيرفر."}
    except Exception as exc:
        return {"status": "error", "message": f"حدث خطأ أثناء طلب رابط المصادقة: {exc}"}

def toggle_account(account_name: str, disabled: bool) -> dict[str, Any]:
    """Enable or disable a specific Antigravity account."""
    oauth_dir = find_oauth_dir()
    target_file = oauth_dir / account_name
    if not target_file.exists():
        # try search in downloads oauth
        alt = Path(r"C:\Users\Samer\Downloads\EasyCLIProxyAPI-v0.2.99-Windows-amd64\EasyCLIProxyAPI-v0.2.99-Windows-amd64\oauth") / account_name
        if alt.exists():
            target_file = alt

    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            d["disabled"] = disabled
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            return {"status": "success", "message": f"تم {'تعطيل' if disabled else 'تفعيل'} الحساب بنجاح."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": "ملف الحساب غير موجود."}

def delete_account(account_name: str) -> dict[str, Any]:
    """Remove an Antigravity account from the pool."""
    # Call management API if running
    if is_cpa_running():
        try:
            url = f"/v8/management/credentials?name={urllib.parse.quote(account_name)}"
            _make_management_request(url, method="DELETE")
        except Exception:
            pass

    # Also delete file locally
    for base in [find_oauth_dir(), Path(r"C:\Users\Samer\Downloads\EasyCLIProxyAPI-v0.2.99-Windows-amd64\EasyCLIProxyAPI-v0.2.99-Windows-amd64\oauth")]:
        f = base / account_name
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    return {"status": "success", "message": "تم حذف الحساب بنجاح من المنظومة."}
