"""Critical path tracking — CPU-only parallel task decomposition."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable


@dataclass
class CriticalPathSnapshot:
    wall_time_ms: float
    slowest_task: str
    parallel_degree: int
    serial_collapse: bool


def decompose_and_run(
    tasks: list[tuple[str, Callable[[], None]]],
    max_workers: int = 4,
    serial_collapse_threshold_ms: float = 5000.0,
) -> CriticalPathSnapshot:
    """CPU-only horizontal split. Never spawns parallel Ollama GPU calls."""
    if not tasks:
        return CriticalPathSnapshot(0.0, "none", 0, False)

    if len(tasks) == 1:
        name, fn = tasks[0]
        t0 = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - t0) * 1000
        return CriticalPathSnapshot(elapsed, name, 1, False)

    t0 = time.perf_counter()
    slowest = ("", 0.0)
    workers = min(max_workers, len(tasks))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks}
        for fut in as_completed(futures):
            name = futures[fut]
            fut.result()
            # Approximate per-task time as share of wall (conservative)
            elapsed = (time.perf_counter() - t0) * 1000
            if elapsed > slowest[1]:
                slowest = (name, elapsed)

    wall_ms = (time.perf_counter() - t0) * 1000
    serial_collapse = workers > 1 and wall_ms > serial_collapse_threshold_ms * len(tasks) * 0.8
    return CriticalPathSnapshot(wall_ms, slowest[0], workers, serial_collapse)
