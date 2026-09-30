# KemetLab — Local Autonomous Multi-Agent Lab

This framework runs decentralized self-organizing teams of AI agents using frontier reasoning and smart tier routing.

## Model tiers (by difficulty)

| Tier | Model | When |
|------|--------|------|
| **Heavy** | `qwen3.5-9b-gguf:ud-q4_k_xl` | Propose, complex peer review, large context |
| **Light** | `qwen3.5:0.8b-gguf` | JSON repair, shard summaries, short tasks |

Routing is automatic (`tier=auto`) via `local/llm/difficulty.py`. Config: `local/config/routing.yaml`.

## Quick start

```powershell
cd AutoScientists-Local
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

ollama pull qwen3.5-9b-gguf:ud-q4_k_xl
ollama pull qwen3.5:0.8b-gguf

.\run_local.ps1 -Name my_run -Cycles 3
```

Or step by step:

```powershell
python launch.py my_run --task task-smoke-local --run --cycles 1
```

## What was removed

- Claude Code orchestration (`claude -p ...`)
- ClawInstitute on port 3000 (not required for `--runtime local`)
- Default cloud API dependency in `launch.py`

Upstream `runbook.md` / HEARTBEAT agents remain in `system/` for reference only.

See [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) for VRAM and Ollama details.

## Dashboard (متابعة الشغل)

```powershell
.\scripts\run_dashboard.ps1
```

افتح المتصفح على: **http://localhost:8501**

تعرض اللوحة:
- **val_loss** عبر الدورات
- جدول KEEP / DISCARD
- مراحل FSM من `logs/sessions.jsonl`
- ملخص Graph-RAG من `logs/graph.db`

اختر مجلد التجربة من القائمة (مثل `C:\Users\Samer\qwen_test`) أو الصق المسار يدوياً.

### تبويب «بحث / Chat» (شبيه وكيل Cursor)

- اكتب **فكرتك البحثية** في صندوق الشات.
- الوكيل يقرأ `champion.json`، `experiments.jsonl`، و`graph.db` ويجيب: ماذا وُجد، ماذا نجح/فشل، واقتراح خطوة تالية.
- المحادثة تُحفظ في `logs/chat.jsonl` داخل مجلد التجربة.
