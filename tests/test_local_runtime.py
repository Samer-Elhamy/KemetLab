"""Unit tests for local runtime (mock LLM)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

os.environ["LOCAL_MOCK_LLM"] = "1"

from local.memory.graph_store import GraphStore
from local.memory.retrieve import build_prompt, truncate_to_budget, _est_tokens
from local.llm.difficulty import score_difficulty
from local.orchestrator.critical_path import decompose_and_run
from local.orchestrator.runner import run_iteration
from local.launch_local import bootstrap_local_run


class TestLocalRuntime(unittest.TestCase):
    def test_prompt_budget(self):
        anchor = "x" * 100
        body = "y" * 20000
        out = truncate_to_budget(anchor, body, max_tokens=4096)
        self.assertLessEqual(_est_tokens(out), 4096 + 64)

    def test_difficulty_routing(self):
        light = score_difficulty("json_repair", "fix json", "return approved bool")
        self.assertEqual(light.tier, "light")
        heavy = score_difficulty("propose", "x" * 5000, "hypothesis champion graph")
        self.assertEqual(heavy.tier, "heavy")

    def test_critical_path_parallel(self):
        results = []

        def a():
            results.append("a")

        def b():
            results.append("b")

        snap = decompose_and_run([("a", a), ("b", b)], max_workers=2)
        self.assertEqual(len(results), 2)
        self.assertGreater(snap.parallel_degree, 0)

    def test_full_iteration_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = _REPO
            run_dir = Path(tmp) / "smoke_test"
            task_path = template / "task-smoke-local"
            bootstrap_local_run(template, run_dir, task_path, "optimization")
            out = run_iteration(run_dir, cycle=1)
            self.assertIn(out["state"], ("done",))
            self.assertTrue((run_dir / "logs" / "experiments.jsonl").exists())
            champ = json.loads((run_dir / "champion.json").read_text())
            self.assertIn("val_loss", champ)
            store = GraphStore(run_dir)
            self.assertGreater(store.g.number_of_nodes(), 0)
            store.close()


if __name__ == "__main__":
    unittest.main()
