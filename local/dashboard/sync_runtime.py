"""Refresh runtime modules in old mission folders."""

from __future__ import annotations

import shutil
from pathlib import Path


def sync_runtime_from_repo(run_dir: Path, repo_root: Path) -> None:
    """Copy orchestrator + llm from repo into run_dir (fixes stale copies)."""
    run_dir = Path(run_dir).resolve()
    repo_root = Path(repo_root).resolve()
    for sub in ("orchestrator", "llm", "config"):
        src = repo_root / "local" / sub
        if not src.is_dir():
            continue
        dst = run_dir / "local" / sub
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.name == "__pycache__":
                continue
            if item.is_file():
                shutil.copy2(item, dst / item.name)
            elif item.is_dir():
                shutil.copytree(item, dst / item.name, dirs_exist_ok=True)
