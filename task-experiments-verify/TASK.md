---
name: experiments-local-verify
task_type: optimization
metric: val_loss
direction: minimize
---

# تحقق: النسخة التجريبية تعمل محلياً بالكامل

مهمة تحقق على **AutoScientists-Local-Experiments** — بدون OpenRouter/Gemini.

## متطلبات التشغيل

- `LOCAL_ONLY=1`
- `LOCAL_LLM_PROVIDER=ollama`
- `LOCAL_PROPOSE_MODE=guided`
- `LOCAL_PEER_REVIEW=local`
- `LOCAL_TEAM_MODE=0`

## معايير النجاح

1. **3 دورات FSM** تكتمل بدون خطأ (KEEP أو DISCARD)
2. لا استدعاء OpenRouter (راجع السجل: لا `[OpenRouter]`)
3. `train.py` ينفّذ في كل دورة
4. النتائج في `logs/experiments.jsonl`

## تشغيل

```powershell
cd C:\Users\Samer\AutoScientists-Local
.\scripts\run_experiments_verify_mission.ps1
```
