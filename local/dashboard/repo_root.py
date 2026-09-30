"""Resolve the real AutoScientists-Local repo (not a copied run folder)."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """
    Walk parents from `start` until we find launch.py + task-smoke-local.
    Avoids treating C:\\Users\\...\\dashboard_xxx as the repo when app.py was copied.
    """
    start = (start or Path(__file__)).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "launch.py").is_file() and (candidate / "task-smoke-local" / "TASK.md").is_file():
            return candidate
    return start.parents[2]


def ensure_repo_on_syspath() -> Path:
    import sys

    repo = find_repo_root()
    rs = str(repo.resolve())
    while rs in sys.path:
        sys.path.remove(rs)
    sys.path.insert(0, rs)
    return repo
