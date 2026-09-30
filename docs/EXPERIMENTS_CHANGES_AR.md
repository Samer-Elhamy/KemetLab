# التعديلات على النسخة التجريبية (AutoScientists-Local-Experiments)

## الهدف
تشغيل **محلي فقط** على جهاز ~6GB VRAM — كفاءة عالية، تضحية طفيفة في الدقة.

## الملفات المعدّلة

| الملف | التعديل |
|-------|---------|
| `local/llm/ollama_client.py` | `LOCAL_ONLY=1` → Ollama فقط (لا OpenRouter/Gemini). `requests.Session()` pooling. `num_ctx=1536`. tokens أقل (256/128). |
| `local/config/routing.yaml` | Qwen **heavy** للـ Propose، **light** للمراجعة والمهام القصيرة. |
| `local/memory/retrieve.py` | prompts أقصر: `MAX_PROMPT_TOKENS=2048`، graph context أصغر (2 blocks / 4 nodes). |
| `local/config/local_only.env` | متغيرات التشغيل المحلي الافتراضية. |
| `EXPERIMENTS_MISSION.json` | علامة تطبيق profile `local_only_v1`. |
| `MISSION_COMPLETE.json` | تحقق اكتمال المهمة (benchmark + smoke). |

## سلوك التشغيل

- **Propose:** `guided` — بحث معاملات بدون انتظار سحابة
- **Peer review:** `local` — فحص حدود محلي (سريع)
- **Execute:** `train.py` + PyTorch
- **عند تشغيل Ollama:** Qwen `qwen3.5:0.8b` heavy/light حسب `routing.yaml`

## ما لم يُمس

- `C:\Users\Samer\AutoScientists-Local` (الإنتاج) — للمقارنة واللوحة

## تحقق

```powershell
cd C:\Users\Samer\AutoScientists-Local
.\scripts\run_experiments_verify_mission.ps1
```
