"""Kaggle Kernel Bundle Generator & Metadata Manager.

Prepares push-ready Kaggle kernel bundles with kernel-metadata.json and
parameter-injected execution scripts.
"""

from __future__ import annotations

import ast
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def detect_kaggle_username(kaggle_json_path: Optional[Union[Path, str]] = None) -> str:
    """Detect Kaggle username from kaggle.json or fall back to default."""
    candidates: List[Path] = []
    if kaggle_json_path is not None:
        candidates.append(Path(kaggle_json_path))

    kaggle_config_dir = os.environ.get("KAGGLE_CONFIG_DIR")
    if kaggle_config_dir:
        candidates.append(Path(kaggle_config_dir) / "kaggle.json")

    candidates.append(Path.home() / ".kaggle" / "kaggle.json")
    candidates.append(Path("C:/Users/Samer/.kaggle/kaggle.json"))

    for p in candidates:
        try:
            if p.exists() and p.is_file():
                raw = p.read_text(encoding="utf-8").strip()
                if raw:
                    data = json.loads(raw)
                    username = data.get("username")
                    if username and isinstance(username, str) and username.strip():
                        return username.strip()
        except Exception:
            continue

    return "samerelhamy"


def build_env_vars(params: Dict[str, Any]) -> Dict[str, str]:
    """Map parameter dictionary to environment variables."""
    env_vars: Dict[str, str] = {}

    if "lr" in params:
        env_vars["SMOKE_LR"] = str(params["lr"])
    if "hidden_dim" in params:
        env_vars["SMOKE_HIDDEN"] = str(params["hidden_dim"])
    elif "hidden" in params:
        env_vars["SMOKE_HIDDEN"] = str(params["hidden"])
    if "steps" in params:
        env_vars["SMOKE_STEPS"] = str(params["steps"])

    for k, v in params.items():
        env_vars[str(k).upper()] = str(v)

    return env_vars


def inject_params_into_script(script_content: str, params: Dict[str, Any]) -> str:
    """Inject parameter environment variables into the script content safely."""
    env_vars = build_env_vars(params)
    if not env_vars:
        return script_content

    # Determine insertion point (must follow docstrings / from __future__ imports)
    insert_line = 0
    try:
        tree = ast.parse(script_content)
        for node in tree.body:
            if (
                isinstance(node, ast.Expr)
                and isinstance(getattr(node, "value", None), ast.Constant)
                and isinstance(node.value.value, str)
                and insert_line == 0
            ):
                insert_line = max(insert_line, getattr(node, "end_lineno", 0))
                continue
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                insert_line = max(insert_line, getattr(node, "end_lineno", 0))
                continue
            break
    except SyntaxError:
        insert_line = 0

    lines = script_content.splitlines(keepends=True)

    # If first line is a shebang, ensure we insert below it
    if insert_line == 0 and lines and lines[0].startswith("#!"):
        insert_line = 1

    injection_lines = [
        "\n# --- AutoScientists Parameter Injection ---\n",
        "import os\n",
    ]
    for k in sorted(env_vars.keys()):
        val = env_vars[k]
        injection_lines.append(f"os.environ[{repr(k)}] = {repr(str(val))}\n")
    injection_lines.append("# ------------------------------------------\n\n")

    combined = lines[:insert_line] + injection_lines + lines[insert_line:]
    return "".join(combined)


def locate_train_script(focus_root: Union[Path, str]) -> Path:
    """Locate train.py under task/repo, repo, or focus_root."""
    root = Path(focus_root)
    candidates = [
        root / "task" / "repo" / "train.py",
        root / "repo" / "train.py",
        root / "train.py",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    raise FileNotFoundError(
        f"Could not find train.py in candidate locations: {[str(c) for c in candidates]}"
    )


def prepare_kaggle_kernel_dir(
    focus_root: Union[Path, str],
    params: Dict[str, Any],
    competition: str = "playground-series-s6e9",
    *,
    kaggle_json_path: Optional[Union[Path, str]] = None,
    run_id: Optional[str] = None,
) -> Path:
    """Prepare a Kaggle kernel bundle directory with metadata and script.py.

    Args:
        focus_root: Root workspace/experiment directory.
        params: Hypotheses/hyperparameters to inject.
        competition: Target competition slug.
        kaggle_json_path: Optional custom path to kaggle.json.
        run_id: Optional custom run id (defaults to as-exp-{uuid}).

    Returns:
        Path to the prepared bundle directory.
    """
    root = Path(focus_root)
    username = detect_kaggle_username(kaggle_json_path)

    if not run_id:
        run_id = f"as-exp-{uuid.uuid4().hex[:8]}"

    # Kaggle slugifies the title; title must resolve to the same slug as id's tail.
    safe_slug = (
        str(run_id)
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
    )
    run_id = safe_slug

    bundle_dir = root / "kaggle_temp" / run_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Format competition sources
    if isinstance(competition, list):
        comp_sources = [str(c) for c in competition if c]
    elif competition:
        comp_sources = [str(competition)]
    else:
        comp_sources = []

    metadata = {
        "id": f"{username}/{run_id}",
        "title": run_id,
        "code_file": "script.py",
        "language": "python",
        "kernel_type": "script",
        # Booleans match working Kaggle kernels on this account (string "true"
        # created unreadable Private Notebook stubs that fail kernels.status).
        "is_private": False,
        "enable_gpu": os.environ.get("AUTOSCIENTISTS_KAGGLE_GPU", "1").strip().lower()
        not in ("0", "false", "no"),
        "enable_internet": True,
        "competition_sources": comp_sources,
        "dataset_sources": [],
        "kernel_sources": [],
    }

    meta_file = bundle_dir / "kernel-metadata.json"
    meta_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    source_train = locate_train_script(root)
    source_content = source_train.read_text(encoding="utf-8")
    script_content = inject_params_into_script(source_content, params)

    script_file = bundle_dir / "script.py"
    script_file.write_text(script_content, encoding="utf-8")

    return bundle_dir
