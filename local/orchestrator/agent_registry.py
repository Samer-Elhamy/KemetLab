"""Local FSM agent roster (visible in dashboard)."""

from __future__ import annotations

from typing import Any

# Each logical agent maps to one or more FSM phases in runner.py
LOCAL_AGENTS: list[dict[str, Any]] = [
    {
        "id": "orchestrator",
        "name_ar": "المنسّق",
        "name_en": "Orchestrator",
        "icon": "🎯",
        "model": "—",
        "role": "يدير الدورة الكاملة ويربط الوكلاء",
    },
    {
        "id": "shard_cpu",
        "name_ar": "وكيل التخطيط",
        "name_en": "Shard / CPU",
        "icon": "📋",
        "model": "CPU",
        "role": "تحليل المسار الحرج وتجميع سياق Graph-RAG",
    },
    {
        "id": "propose",
        "name_ar": "وكيل الاقتراح",
        "name_en": "Propose",
        "icon": "💡",
        "model": "qwen35custom",
        "role": "اقتراح معاملات تجربة جديدة (Tier-1/2)",
    },
    {
        "id": "peer_review",
        "name_ar": "وكيل المراجعة",
        "name_en": "Peer Review",
        "icon": "🔍",
        "model": "qwen35custom",
        "role": "الموافقة أو رفض الاقتراح قبل التنفيذ",
    },
    {
        "id": "execute",
        "name_ar": "وكيل التدريب",
        "name_en": "Execute",
        "icon": "⚙️",
        "model": "train.py",
        "role": "تشغيل التدريب في sandbox وقياس val_loss",
    },
    {
        "id": "ingest",
        "name_ar": "وكيل الاستيعاب",
        "name_en": "Ingest",
        "icon": "📥",
        "model": "CPU",
        "role": "تسجيل النتيجة في الذاكرة والشظايا",
    },
    {
        "id": "graph",
        "name_ar": "وكيل الرسم البياني",
        "name_en": "Graph Update",
        "icon": "🕸️",
        "model": "Graph-RAG",
        "role": "تحديث champion والـ DeadEnds في graph.db",
    },
]

AGENT_BY_ID = {a["id"]: a for a in LOCAL_AGENTS}
