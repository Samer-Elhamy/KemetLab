"""Load experiment run data for the local monitoring dashboard."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


def default_search_roots(template_dir: Path) -> list[Path]:
    parent = template_dir.parent
    return [
        parent,
        Path.home(),
        template_dir,
    ]


def discover_runs(search_roots: list[Path] | None = None, template_dir: Path | None = None) -> list[Path]:
    """Find saved mission / experiment directories."""
    from local.dashboard.missions import discover_missions

    return discover_missions(template_dir)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_champion(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "champion.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def experiments_df(run_dir: Path) -> pd.DataFrame:
    rows = read_jsonl(run_dir / "logs" / "experiments.jsonl")
    if not rows:
        return pd.DataFrame(
            columns=["cycle", "exp_id", "val_loss", "outcome", "ts"]
        )
    df = pd.DataFrame(rows)
    if "params" in df.columns:
        params = pd.json_normalize(df["params"])
        params.columns = [f"param_{c}" for c in params.columns]
        df = pd.concat([df.drop(columns=["params"], errors="ignore"), params], axis=1)
    return df


def sessions_df(run_dir: Path) -> pd.DataFrame:
    rows = read_jsonl(run_dir / "logs" / "sessions.jsonl")
    if not rows:
        return pd.DataFrame()
    flat = []
    for r in rows:
        row = {k: v for k, v in r.items() if k != "critical_path"}
        cp = r.get("critical_path") or {}
        if isinstance(cp, dict):
            row["cp_wall_ms"] = cp.get("wall_time_ms")
            row["cp_slowest"] = cp.get("slowest_task")
            row["cp_parallel"] = cp.get("parallel_degree")
            row["serial_collapse"] = cp.get("serial_collapse")
        flat.append(row)
    return pd.DataFrame(flat)


def graph_summary(run_dir: Path) -> pd.DataFrame:
    db = run_dir / "logs" / "graph.db"
    if not db.exists():
        return pd.DataFrame(columns=["kind", "count"])
    conn = sqlite3.connect(db)
    try:
        cur = conn.execute(
            "SELECT kind, COUNT(*) as count FROM nodes GROUP BY kind ORDER BY count DESC"
        )
        return pd.DataFrame(cur.fetchall(), columns=["kind", "count"])
    finally:
        conn.close()


def run_metadata(run_dir: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {"path": str(run_dir), "name": run_dir.name}
    runtime = run_dir / "RUNTIME"
    if runtime.exists():
        meta["runtime"] = runtime.read_text(encoding="utf-8").strip()
    task_type = run_dir / "TASK_TYPE"
    if task_type.exists():
        meta["task_type"] = task_type.read_text(encoding="utf-8").strip()
    task_md = run_dir / "task" / "TASK.md"
    if task_md.exists():
        meta["task_file"] = str(task_md)
    return meta
