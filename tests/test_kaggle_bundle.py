"""Tests for Kaggle Kernel Bundle Generator & Metadata Manager."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.orchestrator.kaggle_bundle import (
    build_env_vars,
    detect_kaggle_username,
    inject_params_into_script,
    prepare_kaggle_kernel_dir,
)


class TestKaggleBundle(unittest.TestCase):
    def test_detect_username_from_kaggle_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom_kaggle_json = Path(tmp) / "kaggle.json"
            custom_kaggle_json.write_text(
                json.dumps({"username": "testuser123", "key": "abc"}),
                encoding="utf-8",
            )
            self.assertEqual(detect_kaggle_username(custom_kaggle_json), "testuser123")

            empty_json = Path(tmp) / "empty.json"
            empty_json.write_text("{}", encoding="utf-8")
            self.assertEqual(detect_kaggle_username(empty_json), "samerelhamy")

            nonexistent = Path(tmp) / "does_not_exist.json"
            self.assertEqual(detect_kaggle_username(nonexistent), "samerelhamy")

    def test_build_env_vars_mapping(self):
        params = {"lr": 0.03, "hidden_dim": 64, "steps": 500, "model_type": "xgboost"}
        env_vars = build_env_vars(params)
        self.assertEqual(env_vars["SMOKE_LR"], "0.03")
        self.assertEqual(env_vars["SMOKE_HIDDEN"], "64")
        self.assertEqual(env_vars["SMOKE_STEPS"], "500")
        self.assertEqual(env_vars["LR"], "0.03")
        self.assertEqual(env_vars["HIDDEN_DIM"], "64")
        self.assertEqual(env_vars["STEPS"], "500")
        self.assertEqual(env_vars["MODEL_TYPE"], "xgboost")

    def test_prepare_kaggle_kernel_dir_structure_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            focus_root = Path(tmp)
            repo_dir = focus_root / "task" / "repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / "train.py").write_text(
                "import os\nprint(os.environ.get('SMOKE_LR'))\n",
                encoding="utf-8",
            )

            params = {"lr": 0.02, "hidden_dim": 64, "steps": 250, "custom_flag": "alpha"}
            bundle_dir = prepare_kaggle_kernel_dir(
                focus_root=focus_root,
                params=params,
                competition="playground-series-s6e9",
            )

            self.assertTrue(bundle_dir.exists())
            self.assertEqual(bundle_dir.parent, focus_root / "kaggle_temp")
            self.assertTrue(bundle_dir.name.startswith("as-exp-"))

            meta_file = bundle_dir / "kernel-metadata.json"
            self.assertTrue(meta_file.exists())
            meta = json.loads(meta_file.read_text(encoding="utf-8"))

            run_id = bundle_dir.name
            expected_username = detect_kaggle_username()
            self.assertEqual(meta["id"], f"{expected_username}/{run_id}")
            self.assertEqual(meta["title"], f"AutoScientists Run {run_id}")
            self.assertEqual(meta["code_file"], "script.py")
            self.assertEqual(meta["language"], "python")
            self.assertEqual(meta["kernel_type"], "script")
            self.assertEqual(meta["is_private"], False)
            self.assertEqual(meta["enable_gpu"], True)
            self.assertEqual(meta["enable_internet"], True)
            self.assertEqual(meta["competition_sources"], ["playground-series-s6e9"])

    def test_prepare_kaggle_kernel_dir_custom_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            focus_root = Path(tmp)
            repo_dir = focus_root / "repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / "train.py").write_text("print('ok')\n", encoding="utf-8")

            bundle_dir = prepare_kaggle_kernel_dir(
                focus_root,
                params={"lr": 0.1},
                run_id="custom-run-001",
            )
            self.assertEqual(bundle_dir.name, "custom-run-001")
            meta = json.loads((bundle_dir / "kernel-metadata.json").read_text(encoding="utf-8"))
            self.assertIn("/custom-run-001", meta["id"])
            self.assertEqual(meta["title"], "AutoScientists Run custom-run-001")

    def test_prepare_kaggle_kernel_dir_fallback_repo_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            focus_root = Path(tmp)
            # Use repo/train.py instead of task/repo/train.py
            repo_dir = focus_root / "repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / "train.py").write_text("print('fallback repo')\n", encoding="utf-8")

            bundle_dir = prepare_kaggle_kernel_dir(focus_root, params={})
            script_file = bundle_dir / "script.py"
            self.assertTrue(script_file.exists())
            self.assertIn("fallback repo", script_file.read_text(encoding="utf-8"))

    def test_prepare_kaggle_kernel_dir_missing_train_py_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            focus_root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                prepare_kaggle_kernel_dir(focus_root, params={})

    def test_param_injection_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            focus_root = Path(tmp)
            repo_dir = focus_root / "task" / "repo"
            repo_dir.mkdir(parents=True)
            train_code = (
                "import os\n"
                "import json\n"
                "out = {\n"
                "    'smoke_lr': os.environ.get('SMOKE_LR'),\n"
                "    'smoke_hidden': os.environ.get('SMOKE_HIDDEN'),\n"
                "    'smoke_steps': os.environ.get('SMOKE_STEPS'),\n"
                "    'custom': os.environ.get('MY_PARAM'),\n"
                "}\n"
                "print(json.dumps(out))\n"
            )
            (repo_dir / "train.py").write_text(train_code, encoding="utf-8")

            params = {
                "lr": 0.015,
                "hidden_dim": 32,
                "steps": 120,
                "my_param": "hello_kaggle",
            }
            bundle_dir = prepare_kaggle_kernel_dir(focus_root, params=params)
            script_file = bundle_dir / "script.py"
            self.assertTrue(script_file.exists())

            # Verify executing script.py produces expected injected environment variables
            proc = subprocess.run(
                [sys.executable, str(script_file)],
                cwd=str(bundle_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            result = json.loads(proc.stdout.strip())
            self.assertEqual(result["smoke_lr"], "0.015")
            self.assertEqual(result["smoke_hidden"], "32")
            self.assertEqual(result["smoke_steps"], "120")
            self.assertEqual(result["custom"], "hello_kaggle")

    def test_param_injection_with_future_imports_and_docstring(self):
        code = (
            "#!/usr/bin/env python3\n"
            '"""Module docstring here."""\n'
            "from __future__ import annotations\n"
            "\n"
            "import os\n"
            "assert os.environ.get('TEST_KEY') == '123'\n"
        )
        injected = inject_params_into_script(code, {"test_key": "123"})
        # Must compile without SyntaxError (from __future__ must not be preceded by other statements)
        compiled = compile(injected, "<test>", "exec")
        self.assertIsNotNone(compiled)

        # Run in subprocess to check assertion
        proc = subprocess.run(
            [sys.executable, "-c", injected],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"Error: {proc.stderr}")

    def test_with_real_smoke_task(self):
        smoke_dir = _REPO / "task-smoke-local"
        if smoke_dir.exists():
            with tempfile.TemporaryDirectory() as tmp:
                focus_root = Path(tmp) / "smoke"
                import shutil
                shutil.copytree(smoke_dir, focus_root)
                bundle_dir = prepare_kaggle_kernel_dir(
                    focus_root=focus_root,
                    params={"lr": 0.08, "hidden_dim": 8, "steps": 15},
                )
                self.assertTrue((bundle_dir / "kernel-metadata.json").exists())
                self.assertTrue((bundle_dir / "script.py").exists())


if __name__ == "__main__":
    unittest.main()
