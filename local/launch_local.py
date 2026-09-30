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

    def _ignore_local(d: str, names: list[str]) -> list[str]:
        ignored = [n for n in names if n == "__pycache__" or n.endswith(".pyc")]
        if Path(d).name == "local":
            # Never copy code into run dirs — always import from repo (prevents stale agent_tracker).
            ignored.extend(["dashboard", "orchestrator", "llm"])
        return ignored

    shutil.copytree(
        template_dir / "local",
        run_dir / "local",
        ignore=_ignore_local,
        dirs_exist_ok=True,
    )

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

    if task_type == "meta_optimization":
        import json as _json

        meta_base = {
            "val_loss": 9999.0,
            "params": {},
            "direction": "minimize",
            "source": "meta_bootstrap",
            "metric": "resource_score",
        }
        (run_dir / "logs" / "baseline.json").write_text(
            _json.dumps(meta_base, indent=2), encoding="utf-8"
        )
        (run_dir / "champion.json").write_text(
            _json.dumps(meta_base, indent=2), encoding="utf-8"
        )
    else:
        from local.baseline_measure import measure_and_save_baseline

        measure_and_save_baseline(run_dir)

    (run_dir / "RUNTIME").write_text("local\n", encoding="utf-8")
    (run_dir / "TASK_TYPE").write_text(task_type + "\n", encoding="utf-8")

    from local.orchestrator.team_manager import DEFAULT_TEAMS

    teams_yaml = {}
    for t in DEFAULT_TEAMS:
        teams_yaml[t["id"]] = {
            "name_ar": t["name_ar"],
            "hypothesis": t["hypothesis"],
            "prediction": t["prediction"],
            "falsification": t["falsification"],
            "members": ["analyst", "reviewer", "gpu"],
            "workspace": f"teams/{t['id']}",
        }
    import yaml as _yaml

    roster = "---\n" + _yaml.dump({"teams": teams_yaml}, allow_unicode=True) + "---\n\n# فرق محلية (3 فرق متوازية)\n"
    (run_dir / "teams").mkdir(exist_ok=True)
    (run_dir / "teams" / "roster.md").write_text(roster, encoding="utf-8")
    from local.orchestrator.team_manager import ensure_team_workspaces

    for t in DEFAULT_TEAMS:
        ensure_team_workspaces(run_dir, t["id"], t["hypothesis"])

    print(f"  Local runtime bootstrap complete: {run_dir}")
    print(f"  Run: python {template_dir / 'local' / 'orchestrator' / 'runner.py'} --focus-root {run_dir}")
