---
name: meta-local-qwen
task_type: meta_optimization
metric: resource_score
direction: minimize
---

# Meta-Local: تحسين AutoScientists للتشغيل المحلي (Qwen كبير + صغير)

## الهدف

تحسين **نسخة التجارب** (`AUTOSCIENTISTS_TARGET_REPO`) لتعمل **محلياً فقط** على جهاز ~6GB VRAM / 8–16GB RAM:

- **Qwen ثقيل (heavy)**: اقتراحات معقدة، Propose، مراجعة صعبة
- **Qwen خفيف (light)**: JSON repair، ملخصات، مهام قصيرة
- تقسيم المهام بين النموذجين **بقرار الوكلاء** (انظر `local/config/routing.yaml`)

## ما يُقاس (metric: `resource_score`)

كل دورة تشغّل `repo/benchmark.py` على نسخة التجارب. **أقل = أفضل**.

المقياس مركّب (زمن + ذاكرة + نجاح Ollama). تحسّن طفيف في الدقة مقبول إذا انخفض `resource_score` ≥5%.

## مسموح للوكلاء

- تعديل ملفات تحت `local/` في **نسخة التجارب فقط**
- ضبط `local/config/routing.yaml`، prompts، `num_ctx`، `num_gpu`
- قراءة `docs/META_LOCAL_RESEARCH.md` للحلول المقترحة
- **ممنوع** تعديل `C:\Users\Samer\AutoScientists-Local` (النسخة الإنتاجية)

## النسخة الإنتاجية

تستمر في `dashboard_*` على `task-smoke-local` حتى تصبح نسخة التجارب جاهزة للاستبدال.

## معايير KEEP

KEEP إذا `resource_score` **أقل** من البطل الحالي (تحسّن صارم).

## تشغيل

```powershell
$env:AUTOSCIENTISTS_TARGET_REPO = "C:\Users\Samer\AutoScientists-Local-Experiments"
$env:LOCAL_LLM_PROVIDER = "ollama"
python local/orchestrator/meta_runner.py --focus-root <meta_run_dir> --max-cycles 0
```
