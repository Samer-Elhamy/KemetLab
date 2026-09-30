---
name: poker-suspicious-transfers
task_type: optimization
metric: val_loss
direction: minimize
competition: detect-suspicious-value-transfers-in-poker
exec_mode: kaggle
---

# Detect Suspicious Value Transfers in Poker (Kaggle)

Autonomous AutoScientists loop for the Kaggle competition
`detect-suspicious-value-transfers-in-poker`.

## Execution policy (mandatory)
- **ALL heavy training runs on Kaggle cloud GPUs** via `AUTOSCIENTISTS_EXEC_MODE=kaggle`.
- Do **not** train full models on the local laptop GPU/CPU.
- Kernel push only — do **not** call `kaggle competitions submit` unless a
  separate stealth-snipe config is explicitly enabled near deadline.

## Target Metric
- Host metric is maximize (public LB). Internally AutoScientists minimizes
  `val_loss = 1.0 - oof_pair_ap` so lower is better.
- Baseline: quad-blend OOF pair AP from ExtraTrees + CatBoost + LightGBM + XGBoost.
- A result is **KEEP** if it strictly improves (lowers) champion `val_loss`.

## Search Space & Hypotheses
Hyperparameters passed via environment variables into `repo/train.py`:
- `W_CB`, `W_LGB`, `W_ET`, `W_XGB`: ensemble blend weights (auto-normalized)
- `EXP_ID`: experiment label

## Data
- Competition files mounted at `/kaggle/input/.../detect-suspicious-value-transfers-in-poker`
- Hardware: Kaggle GPU kernel (`enable_gpu=true`)
