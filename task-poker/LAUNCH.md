# task-profile.md — poker-suspicious-transfers

Kaggle-cloud runtime profile for `task-poker`.

---

## Hook: launch_command

```powershell
cd C:\Users\Samer\AutoScientists-Local
$env:AUTOSCIENTISTS_EXEC_MODE = "kaggle"
$env:AUTOSCIENTISTS_NO_LOCAL_FALLBACK = "1"
$env:AUTOSCIENTISTS_COMPETITION = "detect-suspicious-value-transfers-in-poker"
$env:AUTOSCIENTISTS_KAGGLE_TIMEOUT = "7200"
$env:LOCAL_TEAM_MODE = "0"
$env:LOCAL_LLM_PROVIDER = "gemini"

.\.venv\Scripts\python launch.py poker_kaggle_v1 --task task-poker --runtime local --run --cycles 3
```

---

## Hook: bootstrap_extras

Sets `RUNTIME=local` for the FSM/LLM side (Gemini via CPA :8317) while
`AUTOSCIENTISTS_EXEC_MODE=kaggle` forces train steps onto Kaggle GPUs.

---

## Hook: discussion_policy

Proposer / Critic / Consensus over blend weights and feature hypotheses.
Never proposes local CUDA training.

---

## Hook: seeding_policy

Seed champion from current best OOF pair AP on the quad-blend baseline
(`val_loss = 1 - oof_pair_ap`).

---

## Hook: gpu_dispatch

GPU execution **only** via Kaggle kernel push (`enable_gpu=true`).
Local fallback is disabled.

---

## Hook: champion_promotion

`local/orchestrator/promotion.py` keeps lower `val_loss`.

---

## Hook: stagnation_response

After 3 consecutive DISCARDs, diversify blend weights and evidence-ranker
routing; still push to Kaggle only.
