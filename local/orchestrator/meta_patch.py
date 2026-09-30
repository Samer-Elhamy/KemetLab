"""Apply bounded search/replace patches to the experiments repo."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_PREFIXES = (
    "local/",
    "local\\",
    "docs/",
    "docs\\",
    "scripts/",
    "scripts\\",
)

FORBIDDEN = (
    ".env",
    "secrets",
    ".key",
    "champion.json",
)


def target_repo() -> Path:
    import os

    p = os.environ.get("AUTOSCIENTISTS_TARGET_REPO", "")
    if not p:
        raise RuntimeError("AUTOSCIENTISTS_TARGET_REPO not set")
    return Path(p).resolve()


def _allowed(path: str) -> bool:
    norm = path.replace("\\", "/")
    if any(x in norm for x in FORBIDDEN):
        return False
    return any(norm.startswith(p.replace("\\", "/")) for p in ALLOWED_PREFIXES)


def apply_changes(changes: list[dict[str, Any]], *, backup_dir: Path | None = None) -> dict[str, Any]:
    repo = target_repo()
    backup_dir = backup_dir or (repo / "logs" / "patch_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    applied: list[str] = []
    errors: list[str] = []

    for i, ch in enumerate(changes):
        rel = str(ch.get("path", "")).replace("\\", "/")
        if not _allowed(rel):
            errors.append(f"forbidden path: {rel}")
            continue
        fp = repo / rel
        if not fp.is_file():
            errors.append(f"missing: {rel}")
            continue
        search = ch.get("search", "")
        replace = ch.get("replace", "")
        text = fp.read_text(encoding="utf-8")
        if search not in text:
            if replace and replace in text:
                applied.append(f"{rel} (already applied)")
                continue
            errors.append(f"search not found in {rel}")
            continue
        if text.count(search) > 1:
            errors.append(f"ambiguous search in {rel} ({text.count(search)} matches)")
            continue
        bak = backup_dir / f"{ts}_{i}_{fp.name}.bak"
        shutil.copy2(fp, bak)
        fp.write_text(text.replace(search, replace, 1), encoding="utf-8")
        applied.append(rel)

    return {"applied": applied, "errors": errors, "ok": len(applied) > 0 and not errors}


def revert_last_backup(backup_dir: Path | None = None) -> bool:
    repo = target_repo()
    backup_dir = backup_dir or (repo / "logs" / "patch_backups")
    if not backup_dir.exists():
        return False
    baks = sorted(backup_dir.glob("*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not baks:
        return False
    # Best-effort: restore most recent backup set (same timestamp prefix)
    latest = baks[0]
    prefix = latest.name.split("_", 2)[0] + "_" + latest.name.split("_", 2)[1]
    restored = 0
    for bak in baks:
        if not bak.name.startswith(prefix):
            continue
        parts = bak.name.split("_", 2)
        if len(parts) < 3:
            continue
        fname = parts[2].replace(".bak", "")
        for rel_root in ALLOWED_PREFIXES:
            for candidate in repo.glob(f"{rel_root.rstrip('/')}/**/{fname}"):
                if candidate.is_file():
                    shutil.copy2(bak, candidate)
                    restored += 1
                    break
    return restored > 0
