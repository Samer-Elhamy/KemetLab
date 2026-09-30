"""Unit tests for Hybrid Execution Switch in Runner."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parents[1]
import sys
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local.orchestrator.runner import _run_train

class TestHybridExecutionSwitch(unittest.TestCase):
    def test_routes_to_kaggle_when_configured(self):
        with patch.dict(os.environ, {"AUTOSCIENTISTS_EXEC_MODE": "kaggle"}):
            with patch("local.orchestrator.kaggle_runner.run_train_kaggle") as mock_kaggle:
                mock_kaggle.return_value = {"val_loss": 0.05123}
                res = _run_train(Path("dummy_root"), {"lr": 0.01})
                assert res["val_loss"] == 0.05123
                mock_kaggle.assert_called_once_with(Path("dummy_root"), {"lr": 0.01})

    def test_routes_to_local_when_mode_is_local(self):
        with patch.dict(os.environ, {"AUTOSCIENTISTS_EXEC_MODE": "local"}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout='{"val_loss": 0.05500}')
                res = _run_train(Path("dummy_root"), {"lr": 0.05})
                assert res["val_loss"] == 0.05500
                assert mock_run.called
