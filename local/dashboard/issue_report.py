"""Build a diagnostic report for Cursor Agent when the dashboard hits an error."""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from local.dashboard.data import load_champion, read_jsonl, run_metadata


def _tail_text(path: Path, max_lines: int = 120) -> str:
    if not path.exists():
        return "(الملف غير موجود)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines) or "(فارغ)"
    return "\n".join(lines[-max_lines:])


def _read_optional(path: Path, max_chars: int = 8000) -> str:
    if not path.exists():
        return "(غير موجود)"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[مختصر]"
    return text


def build_issue_report(
    run_dir: Path | None,
    user_note: str,
    *,
    repo_root: Path,
) -> tuple[Path, str]:
    """
    Write CURSOR_AGENT_ISSUE.md + timestamped copy under .cursor/reports/.
    Returns (report_path, suggested Cursor chat prompt).
    """
    repo_root = repo_root.resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    reports_dir = repo_root / ".cursor" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    from local.dashboard.job_status import read_job_status

    run_dir = Path(run_dir).resolve() if run_dir else None
    job = read_job_status(run_dir) if run_dir else {"state": "no_run"}
    meta = run_metadata(run_dir) if run_dir else {}
    champ = load_champion(run_dir) if run_dir else {}

    sections = [
        "# AutoScientists — تقرير مشكلة للمساعد (Cursor)",
        "",
        f"**وقت التقرير (UTC):** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## وصف المستخدم",
        "",
        user_note.strip() or "(لم يُكتب وصف — تم جمع السجلات تلقائياً)",
        "",
        "## بيئة التشغيل",
        "",
        f"- Python: `{sys.version.split()[0]}` — `{sys.executable}`",
        f"- OS: `{platform.platform()}`",
        f"- LOCAL_MOCK_LLM: `{os.environ.get('LOCAL_MOCK_LLM', '')}`",
        f"- OLLAMA_HOST: `{os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')}`",
        f"- مجلد المشروع: `{repo_root}`",
        "",
    ]

    if run_dir:
        sections.extend(
            [
                "## التجربة",
                "",
                f"- مسار: `{run_dir}`",
                f"- Runtime: `{meta.get('runtime', '?')}`",
                f"- Task type: `{meta.get('task_type', '?')}`",
                "",
                "## حالة المهمة (job_status.json)",
                "",
                "```json",
                json.dumps(job, ensure_ascii=False, indent=2),
                "```",
                "",
                "## Champion",
                "",
                "```json",
                json.dumps(champ, ensure_ascii=False, indent=2),
                "```",
                "",
                "## آخر التجارب (experiments.jsonl)",
                "",
                "```json",
                json.dumps(read_jsonl(run_dir / "logs" / "experiments.jsonl")[-8:], ensure_ascii=False, indent=2),
                "```",
                "",
                "## سجل التشغيل (runner.log)",
                "",
                "```",
                _tail_text(run_dir / "logs" / "runner.log"),
                "```",
                "",
                "## TASK.md",
                "",
                "```markdown",
                _read_optional(run_dir / "task" / "TASK.md", 4000),
                "```",
                "",
                "## هدف المستخدم (user_goal.txt)",
                "",
                "```",
                _read_optional(run_dir / "logs" / "user_goal.txt", 2000),
                "```",
                "",
            ]
        )
    else:
        sections.append("## التجربة\n\n(لم يُختر مجلد تجربة)\n")

    sections.extend(
        [
            "## مطلوب من المساعد",
            "",
            "1. حدّد السبب الجذري من السجلات أعلاه.",
            "2. أصلح الكود في `AutoScientists-Local` (أقل تغيير ممكن).",
            "3. اشرح للمستخدم كيف يعيد تشغيل الداشبورد والتجربة.",
            "",
        ]
    )

    body = "\n".join(sections)
    latest = repo_root / "CURSOR_AGENT_ISSUE.md"
    archived = reports_dir / f"issue_{ts}.md"
    latest.write_text(body, encoding="utf-8")
    archived.write_text(body, encoding="utf-8")

    pointer = {
        "latest": str(latest),
        "archived": str(archived),
        "run_dir": str(run_dir) if run_dir else None,
        "ts": ts,
    }
    (repo_root / ".cursor" / "reports" / "latest_issue.json").write_text(
        json.dumps(pointer, indent=2), encoding="utf-8"
    )

    from local.dashboard.cursor_inbox import _chat_prompt

    prompt = _chat_prompt(repo_root)
    return latest, prompt
