"""Write dashboard errors to AGENT_INBOX.md for the active Cursor chat."""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INBOX_FILENAME = "AGENT_INBOX.md"
PENDING_JSON = ".cursor/dashboard_pending.json"


def _chat_prompt(repo_root: Path) -> str:
    return (
        f"@{INBOX_FILENAME}\n\n"
        "وصلني خطأ من لوحة AutoScientists (Streamlit). اقرأ الملف وصلّح المشروع، "
        "ثم قلّي كيف أعيد تشغيل الداشبورد."
    )


def report_dashboard_error(
    error: BaseException,
    *,
    repo_root: Path,
    run_dir: Path | None = None,
    user_note: str = "",
    source: str = "dashboard",
) -> dict[str, Any]:
    """
    Save error for Cursor Agent (same workspace chat).
    Returns paths + ready-to-paste prompt.
    """
    repo_root = Path(repo_root).resolve()
    ts = datetime.now(timezone.utc).isoformat()
    tb = traceback.format_exc()
    if not tb or tb.strip() == "NoneType: None\n":
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    lines = [
        "# طلب إصلاح — AutoScientists Dashboard",
        "",
        f"**الوقت (UTC):** {ts}",
        f"**المصدر:** {source}",
        "",
        "## الخطأ",
        "",
        "```",
        f"{type(error).__name__}: {error}",
        "```",
        "",
        "## Traceback",
        "",
        "```",
        tb[-12000:],
        "```",
        "",
    ]
    if user_note.strip():
        lines.extend(["## ملاحظة المستخدم", "", user_note.strip(), ""])
    if run_dir:
        lines.extend(["## مجلد التجربة", "", f"`{run_dir}`", ""])

    lines.extend(
        [
            "## مطلوب من المساعد (نفس محادثة Cursor)",
            "",
            "1. أصلح السبب في `AutoScientists-Local`.",
            "2. تأكد أن `python -c \"from local.dashboard.executor import repair_stale_job\"` يعمل.",
            "3. اشرح للمستخدم: `.\scripts\\run_dashboard.ps1`",
            "",
        ]
    )

    body = "\n".join(lines)
    inbox = repo_root / INBOX_FILENAME
    inbox.write_text(body, encoding="utf-8")

    pending = {
        "ts": ts,
        "inbox": str(inbox),
        "error_type": type(error).__name__,
        "error": str(error),
        "prompt": _chat_prompt(repo_root),
        "run_dir": str(run_dir) if run_dir else None,
    }
    pending_path = repo_root / PENDING_JSON
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")

    # Full diagnostic report (optional, richer)
    try:
        from local.dashboard.issue_report import build_issue_report

        build_issue_report(run_dir, user_note or str(error), repo_root=repo_root)
    except Exception:
        pass

    return {
        "inbox_path": str(inbox),
        "pending_path": str(pending_path),
        "prompt": pending["prompt"],
    }


def load_pending(repo_root: Path) -> dict[str, Any] | None:
    path = Path(repo_root) / PENDING_JSON
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
