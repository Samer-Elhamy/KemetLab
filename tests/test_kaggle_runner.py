"""Unit and mock tests for Remote Kaggle Executor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.orchestrator.kaggle_runner import (
    DEFAULT_KAGGLE_EXE,
    _extract_output_metrics,
    extract_output_metrics,
    get_kaggle_exe,
    run_train_kaggle,
)


class TestKaggleRunner(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.focus_root = Path(self.tmp_dir.name)
        # Create minimal repo structure with train.py
        train_dir = self.focus_root / "task" / "repo"
        train_dir.mkdir(parents=True, exist_ok=True)
        (train_dir / "train.py").write_text(
            "import os\nprint('train.py execution')\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_get_kaggle_exe_resolution(self):
        # 1. Custom path override
        self.assertEqual(get_kaggle_exe("custom/path/kaggle.exe"), "custom/path/kaggle.exe")

        # 2. Environment variable override
        with patch.dict(os.environ, {"KAGGLE_EXE": "/custom/bin/kaggle"}):
            self.assertEqual(get_kaggle_exe(), "/custom/bin/kaggle")

        # 3. Default path resolution or fallback
        with patch.dict(os.environ, {}, clear=True):
            exe = get_kaggle_exe()
            self.assertTrue(exe.endswith("kaggle.exe") or exe.endswith("kaggle"))

    def test_extract_metrics_direct_json(self):
        out_dir = self.focus_root / "out1"
        out_dir.mkdir(parents=True)
        metrics_file = out_dir / "metrics.json"
        metrics_file.write_text(
            json.dumps({"val_loss": 0.0425, "roc_auc": 0.9575}),
            encoding="utf-8",
        )

        res = _extract_output_metrics(out_dir)
        self.assertEqual(res["val_loss"], 0.0425)
        self.assertEqual(res["roc_auc"], 0.9575)

    def test_extract_metrics_nested_json(self):
        out_dir = self.focus_root / "out2"
        sub_dir = out_dir / "eval_results"
        sub_dir.mkdir(parents=True)
        (sub_dir / "eval_summary.json").write_text(
            json.dumps({"val_loss": "0.0350", "epoch": 10}),
            encoding="utf-8",
        )

        res = extract_output_metrics(out_dir)
        self.assertAlmostEqual(res["val_loss"], 0.035)
        self.assertEqual(res["epoch"], 10)

    def test_extract_metrics_from_log_json_lines(self):
        out_dir = self.focus_root / "out3"
        out_dir.mkdir(parents=True)
        log_file = out_dir / "kernel_run.log"
        log_file.write_text(
            "Initializing training...\n"
            '{"epoch": 1, "val_loss": 0.5}\n'
            '{"epoch": 2, "val_loss": 0.3}\n'
            '{"val_loss": 0.0275, "roc_auc": 0.9725, "best_iteration": 450}\n'
            "Training completed successfully.\n",
            encoding="utf-8",
        )

        res = _extract_output_metrics(out_dir)
        self.assertEqual(res["val_loss"], 0.0275)
        self.assertEqual(res["roc_auc"], 0.9725)
        self.assertEqual(res["best_iteration"], 450)

    def test_extract_metrics_from_embedded_json(self):
        out_dir = self.focus_root / "out4"
        out_dir.mkdir(parents=True)
        log_file = out_dir / "stdout.txt"
        log_file.write_text(
            "[2026-09-20 12:00:00] [AutoScientists] Final metrics: "
            '{"val_loss": 0.0199, "score": 0.98}\n',
            encoding="utf-8",
        )

        res = _extract_output_metrics(out_dir)
        self.assertEqual(res["val_loss"], 0.0199)
        self.assertEqual(res["score"], 0.98)

    def test_extract_metrics_from_regex_fallback(self):
        out_dir = self.focus_root / "out5"
        out_dir.mkdir(parents=True)
        log_file = out_dir / "output.out"
        log_file.write_text(
            "Training complete.\n"
            "val_loss = 0.0489\n",
            encoding="utf-8",
        )

        res = _extract_output_metrics(out_dir)
        self.assertAlmostEqual(res["val_loss"], 0.0489)

    def test_extract_metrics_missing_raises_runtime_error(self):
        out_dir = self.focus_root / "out6"
        out_dir.mkdir(parents=True)
        (out_dir / "unrelated.txt").write_text("just some logs without metrics\n", encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            _extract_output_metrics(out_dir)
        self.assertIn("No valid metrics containing 'val_loss' found", str(ctx.exception))

    def test_extract_metrics_nonexistent_dir_raises(self):
        nonexistent = self.focus_root / "does_not_exist"
        with self.assertRaises(RuntimeError) as ctx:
            _extract_output_metrics(nonexistent)
        self.assertIn("Output directory does not exist", str(ctx.exception))

    @patch("subprocess.run")
    def test_run_train_kaggle_full_lifecycle_success(self, mock_run):
        # Define mock behavior for subprocess.run:
        # Call 1: push
        # Call 2: status (running)
        # Call 3: status (complete)
        # Call 4: output
        push_result = MagicMock(returncode=0, stdout="Kernel version 1 successfully created", stderr="")
        status_running = MagicMock(returncode=0, stdout="testuser/as-exp-test has status 'running'", stderr="")
        status_complete = MagicMock(returncode=0, stdout="testuser/as-exp-test has status 'complete'", stderr="")

        def side_effect(cmd, **kwargs):
            if cmd[1] == "kernels" and cmd[2] == "push":
                return push_result
            elif cmd[1] == "kernels" and cmd[2] == "status":
                if mock_run.call_count == 2:
                    return status_running
                return status_complete
            elif cmd[1] == "kernels" and cmd[2] == "output":
                # Create the output metrics file in the destination output dir
                out_path = Path(cmd[cmd.index("-p") + 1])
                out_path.mkdir(parents=True, exist_ok=True)
                (out_path / "metrics.json").write_text(
                    json.dumps({"val_loss": 0.0315, "roc_auc": 0.9685}),
                    encoding="utf-8",
                )
                return MagicMock(returncode=0, stdout="Output downloaded", stderr="")
            raise ValueError(f"Unexpected command: {cmd}")

        mock_run.side_effect = side_effect

        fake_kaggle = self.focus_root / "fake_kaggle.json"
        fake_kaggle.write_text(json.dumps({"username": "testuser", "key": "abc"}), encoding="utf-8")

        params = {"lr": 0.03, "hidden_dim": 64, "steps": 200}
        result = run_train_kaggle(
            focus_root=self.focus_root,
            params=params,
            timeout=30,
            poll_interval=0.01,
            kaggle_json_path=fake_kaggle,
            run_id="as-exp-test",
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["val_loss"], 0.0315)
        self.assertEqual(result["roc_auc"], 0.9685)

        # Verify command invocations
        self.assertEqual(mock_run.call_count, 4)
        calls = mock_run.call_args_list
        # Call 1: push
        self.assertIn("push", calls[0][0][0])
        # Call 2: status
        self.assertIn("status", calls[1][0][0])
        self.assertIn("testuser/as-exp-test", calls[1][0][0][3])
        # Call 3: status
        self.assertIn("status", calls[2][0][0])
        # Call 4: output
        self.assertIn("output", calls[3][0][0])
        self.assertIn("-p", calls[3][0][0])

    @patch("subprocess.run")
    def test_run_train_kaggle_push_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="403 - Forbidden: Invalid credentials",
        )

        params = {"lr": 0.01}
        with self.assertRaises(RuntimeError) as ctx:
            run_train_kaggle(
                focus_root=self.focus_root,
                params=params,
                run_id="as-exp-push-fail",
            )
        self.assertIn("Kaggle push failed", str(ctx.exception))
        self.assertIn("403 - Forbidden", str(ctx.exception))

    @patch("subprocess.run")
    def test_run_train_kaggle_status_check_failure(self, mock_run):
        push_ok = MagicMock(returncode=0, stdout="Kernel pushed", stderr="")
        status_err = MagicMock(returncode=1, stdout="", stderr="Network connection reset")

        mock_run.side_effect = [push_ok, status_err]

        params = {"lr": 0.01}
        with self.assertRaises(RuntimeError) as ctx:
            run_train_kaggle(
                focus_root=self.focus_root,
                params=params,
                poll_interval=0.01,
                run_id="as-exp-status-fail",
            )
        self.assertIn("Kaggle status check failed", str(ctx.exception))
        self.assertIn("Network connection reset", str(ctx.exception))

    @patch("subprocess.run")
    def test_run_train_kaggle_kernel_execution_error(self, mock_run):
        push_ok = MagicMock(returncode=0, stdout="Kernel pushed", stderr="")
        status_error = MagicMock(
            returncode=0,
            stdout="Kernel user/as-exp-err has status 'error'",
            stderr="",
        )

        mock_run.side_effect = [push_ok, status_error]

        params = {"lr": 0.01}
        with self.assertRaises(RuntimeError) as ctx:
            run_train_kaggle(
                focus_root=self.focus_root,
                params=params,
                poll_interval=0.01,
                run_id="as-exp-err",
            )
        self.assertIn("failed with status", str(ctx.exception))
        self.assertIn("error", str(ctx.exception))

    @patch("subprocess.run")
    def test_run_train_kaggle_timeout_handling(self, mock_run):
        push_ok = MagicMock(returncode=0, stdout="Kernel pushed", stderr="")
        status_running = MagicMock(
            returncode=0,
            stdout="Kernel user/as-exp-timeout has status 'running'",
            stderr="",
        )

        mock_run.side_effect = [push_ok] + [status_running] * 20

        params = {"lr": 0.01}
        with self.assertRaises(TimeoutError) as ctx:
            run_train_kaggle(
                focus_root=self.focus_root,
                params=params,
                timeout=0.15,
                poll_interval=0.05,
                run_id="as-exp-timeout",
            )
        self.assertIn("timed out after 0.15s", str(ctx.exception))

    @patch("subprocess.run")
    def test_run_train_kaggle_output_pull_failure(self, mock_run):
        push_ok = MagicMock(returncode=0, stdout="Kernel pushed", stderr="")
        status_complete = MagicMock(
            returncode=0,
            stdout="Kernel user/as-exp-out-fail has status 'complete'",
            stderr="",
        )
        output_fail = MagicMock(
            returncode=1,
            stdout="",
            stderr="Could not download output archive",
        )

        mock_run.side_effect = [push_ok, status_complete, output_fail]

        params = {"lr": 0.01}
        with self.assertRaises(RuntimeError) as ctx:
            run_train_kaggle(
                focus_root=self.focus_root,
                params=params,
                poll_interval=0.01,
                run_id="as-exp-out-fail",
            )
        self.assertIn("Kaggle output pull failed", str(ctx.exception))
        self.assertIn("Could not download output archive", str(ctx.exception))

    @patch("subprocess.run")
    def test_run_train_kaggle_custom_output_dir(self, mock_run):
        push_ok = MagicMock(returncode=0, stdout="Kernel pushed", stderr="")
        status_complete = MagicMock(returncode=0, stdout="status 'complete'", stderr="")

        custom_output = self.focus_root / "custom_download_dir"

        def side_effect(cmd, **kwargs):
            if cmd[1] == "kernels" and cmd[2] == "push":
                return push_ok
            elif cmd[1] == "kernels" and cmd[2] == "status":
                return status_complete
            elif cmd[1] == "kernels" and cmd[2] == "output":
                p_idx = cmd.index("-p")
                target_p = Path(cmd[p_idx + 1])
                target_p.mkdir(parents=True, exist_ok=True)
                (target_p / "metrics.json").write_text(
                    json.dumps({"val_loss": 0.0111}),
                    encoding="utf-8",
                )
                return MagicMock(returncode=0, stdout="Downloaded", stderr="")
            raise ValueError(f"Unexpected: {cmd}")

        mock_run.side_effect = side_effect

        res = run_train_kaggle(
            focus_root=self.focus_root,
            params={"lr": 0.05},
            output_dir=custom_output,
            poll_interval=0.01,
            run_id="as-exp-custom-out",
        )
        self.assertEqual(res["val_loss"], 0.0111)
        self.assertTrue((custom_output / "metrics.json").exists())


if __name__ == "__main__":
    unittest.main()
