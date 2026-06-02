"""Bootstrap a local-runtime experiment directory (no ClawInstitute)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def bootstrap_local_run(
    template_dir: Path,
    run_dir: Path,
    task_path: Path,
    task_type: str,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(template_dir / "system", run_dir / "system", dirs_exist_ok=True)
    shutil.copytree(template_dir / "local", run_dir / "local", dirs_exist_ok=True)

    def _ignore(d: str, names: list[str]) -> list[str]:
        return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]

    shutil.copytree(task_path, run_dir / "task", ignore=_ignore, dirs_exist_ok=True)

    launch_md = task_path / "LAUNCH.md"
    if not launch_md.exists():
        for parent in [task_path, *task_path.parents]:
            if (parent / "LAUNCH.md").exists():
                launch_md = parent / "LAUNCH.md"
                break
    if launch_md.exists():
        shutil.copy2(launch_md, run_dir / "task-profile.md")

    (run_dir / "logs" / "raw").mkdir(parents=True, exist_ok=True)
    (run_dir / "champion").mkdir(exist_ok=True)

    champ = {
        "val_loss": 999.0,
        "params": {"lr": 0.1, "hidden_dim": 8, "steps": 10},
        "direction": "minimize",
    }
    (run_dir / "champion.json").write_text(json.dumps(champ, indent=2), encoding="utf-8")

    (run_dir / "RUNTIME").write_text("local\n", encoding="utf-8")
    (run_dir / "TASK_TYPE").write_text(task_type + "\n", encoding="utf-8")

    roster = """---
teams:
  smoke:
    workspace_id: local
    members: [local_worker]
    hypothesis: Minimize val_loss via hyperparameter search
---

# Roster (local smoke)
"""
    (run_dir / "teams").mkdir(exist_ok=True)
    (run_dir / "teams" / "roster.md").write_text(roster, encoding="utf-8")

    print(f"  Local runtime bootstrap complete: {run_dir}")
    print(f"  Run: python {template_dir / 'local' / 'orchestrator' / 'runner.py'} --focus-root {run_dir}")
