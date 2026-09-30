"""Remote Kaggle Executor with CLI Lifecycle Management.

Orchestrates remote Kaggle kernel execution:
1. Prepares bundle dir via prepare_kaggle_kernel_dir
2. Pushes kernel using Kaggle CLI
3. Polls status until complete, failed, or timed out
4. Pulls kernel output files
5. Extracts training metrics (val_loss) from output
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from local.orchestrator.kaggle_bundle import prepare_kaggle_kernel_dir

DEFAULT_KAGGLE_EXE = r"C:\Users\Samer\kaggle\.venv\Scripts\kaggle.exe"


def get_kaggle_exe(custom_path: Optional[Union[str, Path]] = None) -> str:
    """Resolve Kaggle CLI executable path."""
    if custom_path:
        return str(custom_path)
    env_path = os.environ.get("KAGGLE_EXE")
    if env_path:
        return env_path
    if Path(DEFAULT_KAGGLE_EXE).exists():
        return DEFAULT_KAGGLE_EXE
    which = shutil.which("kaggle")
    if which:
        return which
    return "kaggle"


def _extract_output_metrics(output_dir: Union[Path, str]) -> Dict[str, Any]:
    """Extract metrics dictionary containing 'val_loss' from Kaggle output directory.

    Checks:
    1. metrics.json directly in output_dir
    2. Any *.json file in output_dir (recursive)
    3. Log files (*.log, *.txt, *.out) scanned for JSON lines or val_loss text
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        raise RuntimeError(f"Output directory does not exist: {output_path}")

    # 1. Direct metrics.json
    direct_metrics = output_path / "metrics.json"
    if direct_metrics.is_file():
        try:
            data = json.loads(direct_metrics.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "val_loss" in data:
                data["val_loss"] = float(data["val_loss"])
                return data
        except Exception:
            pass

    # 2. Any JSON file in output_path (except metadata)
    for json_file in sorted(output_path.rglob("*.json")):
        if json_file.name == "kernel-metadata.json":
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "val_loss" in data:
                data["val_loss"] = float(data["val_loss"])
                return data
        except Exception:
            continue

    # 3. Log / text / console output files
    candidate_files = []
    for f in sorted(output_path.rglob("*")):
        if f.is_file() and not f.name.endswith(".json"):
            if f.suffix.lower() in (".log", ".txt", ".out"):
                candidate_files.insert(0, f)
            else:
                candidate_files.append(f)

    for f in candidate_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.splitlines()
        # Scan in reverse to catch the latest/final metrics line
        for line in reversed(lines):
            line = line.strip()
            if not line or "val_loss" not in line:
                continue

            data = None
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                except Exception:
                    data = None

            if data is None:
                start_idx = line.find("{")
                end_idx = line.rfind("}")
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    try:
                        data = json.loads(line[start_idx : end_idx + 1])
                    except Exception:
                        data = None

            if isinstance(data, dict) and "val_loss" in data:
                data["val_loss"] = float(data["val_loss"])
                return data

            # Fallback regex for val_loss: <number>
            match = re.search(
                r"['\"]?val_loss['\"]?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)",
                line,
            )
            if match:
                return {"val_loss": float(match.group(1))}

    raise RuntimeError(
        f"No valid metrics containing 'val_loss' found in Kaggle output directory: {output_path}"
    )


extract_output_metrics = _extract_output_metrics


def run_train_kaggle(
    focus_root: Union[Path, str],
    params: Dict[str, Any],
    timeout: int = 1200,
    *,
    competition: str = "playground-series-s6e9",
    kaggle_json_path: Optional[Union[Path, str]] = None,
    kaggle_exe: Optional[Union[Path, str]] = None,
    poll_interval: float = 15.0,
    run_id: Optional[str] = None,
    output_dir: Optional[Union[Path, str]] = None,
) -> Dict[str, Any]:
    """Execute training remotely on Kaggle via Kaggle CLI.

    Args:
        focus_root: Root workspace/experiment directory.
        params: Hypotheses / hyperparameters dictionary to inject.
        timeout: Total timeout in seconds for execution (default 1200).
        competition: Target competition slug.
        kaggle_json_path: Optional custom path to kaggle.json.
        kaggle_exe: Optional custom path to kaggle executable.
        poll_interval: Seconds between status polls (default 15.0).
        run_id: Optional custom run id.
        output_dir: Optional custom directory to download outputs to.

    Returns:
        Dict containing training metrics with 'val_loss'.
    """
    root = Path(focus_root)
    exe = get_kaggle_exe(kaggle_exe)

    # 1. Prepare Kaggle kernel bundle
    bundle_dir = prepare_kaggle_kernel_dir(
        focus_root=root,
        params=params,
        competition=competition,
        kaggle_json_path=kaggle_json_path,
        run_id=run_id,
    )

    # 2. Read kernel slug from metadata
    meta_file = bundle_dir / "kernel-metadata.json"
    if not meta_file.exists():
        raise FileNotFoundError(
            f"kernel-metadata.json not found in bundle: {bundle_dir}"
        )

    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    kernel_slug = meta.get("id")
    if not kernel_slug:
        raise ValueError(f"Kernel metadata missing 'id' slug: {meta_file}")

    # 3. Push kernel to Kaggle
    push_cmd = [exe, "kernels", "push", "-p", str(bundle_dir)]
    push_proc = subprocess.run(push_cmd, capture_output=True, text=True, timeout=300)
    push_out = f"{push_proc.stdout or ''}\n{push_proc.stderr or ''}"
    push_lower = push_out.lower()
    if push_proc.returncode != 0 or any(
        bad in push_lower
        for bad in (
            "client error",
            "409 ",
            "403 ",
            "401 ",
            "permission",
            "does not resolve",
            "kernel push error",
            "maximum batch gpu",
            "session count",
        )
    ):
        raise RuntimeError(
            f"Kaggle push failed for {kernel_slug} (exit code {push_proc.returncode}):\n"
            f"STDOUT: {push_proc.stdout}\n"
            f"STDERR: {push_proc.stderr}"
        )

    # Brief settle time before first status poll (new kernels are eventually consistent)
    time.sleep(min(5.0, poll_interval))

    # 4. Poll status until complete, error, or timeout
    status_cmd = [exe, "kernels", "status", kernel_slug]
    start_time = time.monotonic()

    while True:
        status_proc = subprocess.run(
            status_cmd, capture_output=True, text=True, timeout=60
        )
        if status_proc.returncode != 0:
            raise RuntimeError(
                f"Kaggle status check failed for {kernel_slug} (exit code {status_proc.returncode}):\n"
                f"STDOUT: {status_proc.stdout}\n"
                f"STDERR: {status_proc.stderr}"
            )

        status_text = (status_proc.stdout or "").strip()
        status_lower = status_text.lower()

        if "complete" in status_lower:
            break

        if any(err_word in status_lower for err_word in ("error", "failed", "cancel")):
            raise RuntimeError(
                f"Kaggle kernel {kernel_slug} failed with status: {status_text}"
            )

        elapsed = time.monotonic() - start_time
        if elapsed >= timeout:
            raise TimeoutError(
                f"Kaggle kernel {kernel_slug} timed out after {timeout}s. Last status: {status_text}"
            )

        sleep_time = min(poll_interval, max(0.1, timeout - elapsed))
        time.sleep(sleep_time)

    # 5. Pull output files
    if output_dir is not None:
        target_output_dir = Path(output_dir)
    else:
        target_output_dir = bundle_dir / "output"

    target_output_dir.mkdir(parents=True, exist_ok=True)

    output_cmd = [exe, "kernels", "output", kernel_slug, "-p", str(target_output_dir)]
    output_proc = subprocess.run(
        output_cmd, capture_output=True, text=True, timeout=300
    )
    if output_proc.returncode != 0:
        raise RuntimeError(
            f"Kaggle output pull failed for {kernel_slug} (exit code {output_proc.returncode}):\n"
            f"STDOUT: {output_proc.stdout}\n"
            f"STDERR: {output_proc.stderr}"
        )

    # 6. Extract metrics
    metrics = _extract_output_metrics(target_output_dir)
    return metrics


__all__ = [
    "DEFAULT_KAGGLE_EXE",
    "get_kaggle_exe",
    "extract_output_metrics",
    "_extract_output_metrics",
    "run_train_kaggle",
]
