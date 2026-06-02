"""Research chat agent — answers from local run evidence (Cursor-style)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local.dashboard.data import (
    experiments_df,
    graph_summary,
    load_champion,
    read_jsonl,
    run_metadata,
)
from local.llm.chat import generate_chat, stream_chat

SYSTEM_PROMPT = """أنت مساعد بحث محلي لـ AutoScientists (qwen35custom). مهمتك:
1. الإجابة بناءً على **الأدلة المرفقة فقط** (champion، تجارب، graph) — لا تختلق نتائج.
2. اربط إجابتك **بفكرة المستخدم البحثية** وقل بوضوح: ماذا تم تجربته، ماذا نجح (KEEP)، ماذا فشل (DISCARD)، وأين وصلنا الآن.
3. اقترح **خطوة تالية واحدة** محددة (معاملات أو اتجاه) إن أمكن.
4. استخدم عربية واضحة مع مصطلحات تقنية إنجليزية عند الحاجة.
5. إن لم توجد تجارب بعد، قل ذلك صراحة واقترح تشغيل: launch.py --run

لا تستخدم JSON في الرد — نص منسّق بعناوين قصيرة ونقاط."""


def _task_excerpt(run_dir: Path, max_chars: int = 1500) -> str:
    task = run_dir / "task" / "TASK.md"
    if not task.exists():
        return "(لا يوجد TASK.md)"
    text = task.read_text(encoding="utf-8")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[مختصر]"
    return text


def _graph_highlights(run_dir: Path) -> str:
    db = run_dir / "logs" / "graph.db"
    if not db.exists():
        return "(لا graph.db)"
    import sqlite3

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT id, kind, data FROM nodes ORDER BY rowid DESC LIMIT 12"
        ).fetchall()
    finally:
        conn.close()
    lines = []
    for nid, kind, data in rows:
        try:
            d = json.loads(data)
        except json.JSONDecodeError:
            d = {"raw": data[:200]}
        lines.append(f"- [{kind}] {nid}: {json.dumps(d, ensure_ascii=False)[:300]}")
    return "\n".join(lines) if lines else "(فارغ)"


def build_evidence_snapshot(run_dir: Path, user_idea: str = "") -> str:
    meta = run_metadata(run_dir)
    champ = load_champion(run_dir)
    exps = read_jsonl(run_dir / "logs" / "experiments.jsonl")
    recent = exps[-8:] if exps else []
    gsum = graph_summary(run_dir)

    parts = [
        f"## تجربة: {meta.get('name', run_dir.name)}",
        f"مسار: {run_dir}",
        f"نوع المهمة: {meta.get('task_type', '?')}",
        "",
        "## فكرة المستخدم الحالية",
        user_idea or "(لم تُحدد بعد)",
        "",
        "## Champion الحالي",
        json.dumps(champ, ensure_ascii=False, indent=2),
        "",
        "## آخر التجارب",
    ]
    if recent:
        for e in recent:
            parts.append(
                f"- cycle {e.get('cycle')}: {e.get('outcome')} val_loss={e.get('val_loss')} "
                f"params={e.get('params')}"
            )
    else:
        parts.append("(لا تجارب بعد)")

    parts.extend(
        [
            "",
            "## ملخص Graph-RAG",
            gsum.to_string() if not gsum.empty else "(فارغ)",
            "",
            "## عقد حديثة",
            _graph_highlights(run_dir),
            "",
            "## موجز المهمة",
            _task_excerpt(run_dir),
        ]
    )
    return "\n".join(parts)


def append_chat_log(run_dir: Path, role: str, content: str) -> None:
    path = run_dir / "logs" / "chat.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "role": role,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_chat_history(run_dir: Path) -> list[dict[str, str]]:
    rows = read_jsonl(run_dir / "logs" / "chat.jsonl")
    return [{"role": r["role"], "content": r["content"]} for r in rows if "role" in r]


def format_conversation_turns(history: list[dict[str, str]], limit: int = 6) -> str:
    tail = history[-limit:]
    if not tail:
        return ""
    lines = ["## محادثة سابقة"]
    for m in tail:
        role = "مستخدم" if m["role"] == "user" else "مساعد"
        lines.append(f"**{role}:** {m['content'][:400]}")
    return "\n".join(lines)


def research_reply(
    run_dir: Path,
    user_message: str,
    history: list[dict[str, str]] | None = None,
    *,
    stream: bool = True,
):
    """Returns str or generator of str chunks if stream=True."""
    history = history or []
    evidence = build_evidence_snapshot(run_dir, user_idea=user_message)
    conv = format_conversation_turns(history[:-1] if history else [])
    prompt = f"{evidence}\n\n{conv}\n\n## السؤال الجديد\n{user_message}"

    if stream:
        return stream_chat(prompt, SYSTEM_PROMPT, tier="auto")
    return generate_chat(prompt, SYSTEM_PROMPT, tier="auto")
