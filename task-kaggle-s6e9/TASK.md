---
name: kaggle-s6e9
task_type: optimization
metric: roc_auc
direction: maximize
---

# Kaggle Playground S6E9: Predicting Electric Vehicle Purchases

Autonomous scientific agent optimization loop for **Rank 1 only** on the Kaggle leaderboard.

## Standing orders (Samer)
- Accept **nothing below Rank 1**.
- **Zero local download/train** — execution must use Kaggle cloud (`AUTOSCIENTISTS_EXEC_MODE=kaggle` / `kaggle_runner`).
- Local box = cockpit (hypotheses, FSM, kernel push/pull) only.
- **Kaggle submit only on a large jump** toward #1: expected Public **≥ 0.94703** (prefer **≥ 0.94720**). Tiny OOF wins → KEEP in ledger, **no competition submit**.

## Target Metric
- **roc_auc**: Area under the ROC curve (higher is better - maximize).
- Internal FSM Champion baseline (CV): **0.94293** (5-Fold LightGBM) / blend ~**0.94314**.
- Current best **Public** anchor: **0.94657** (jazivxt/megayak/defiaudit family).
- Leader #1 ≈ **0.94703** — operational target **≥ 0.94720**.
- A result is **KEEP** if it strictly improves the AutoScientists champion metric **and** is on a path to Rank 1 (not a dead-end weak tree blend).
- Any modification causing leakage, regression in CV, or NaNs is recorded in the **Dead-End Ledger**.

## Search Space & Hypotheses
Hyperparameters and feature engineering flags passed via environment variables to `repo/train.py` (runs on **Kaggle**, not locally):
- `FEATURE_SET`: `base`, `domain_rules`, `deotte_recipe`, `target_encoding`, `triple_te_smooth_keys`, `all`
- `COMPETITION_DATA_ONLY`: Strict compliance — zero external datasets, zero leaked priors
- `MODEL_FAMILY`: `lightgbm`, `xgboost_gpu`, `catboost`, `realmlp_gpu`
- `LEARNING_RATE`: `0.02` - `0.08`
- `NUM_LEAVES`: `31` - `127`
- `MAX_DEPTH`: `4` - `8`
- `SUBSAMPLE`: `0.6` - `0.9`
- `COLSAMPLE`: `0.6` - `0.9`
- `REG_ALPHA`: `1e-5` - `1.0`
- `REG_LAMBDA`: `1e-5` - `5.0`
- `POST_PROCESSING`: `continuous_micro_rank_blend` (w=0.015), `calibrated_band_swaps`, `multi_stream_meta`
- Prefer hypotheses that can beat **public anchors** (jazivxt/megayak/DGP), not only internal 0.943 OOF.

## Data
- Competition data accessed **on Kaggle kernels** via competition/dataset sources — do not re-download full dumps to the laptop for training.
- Hardware for training: **Kaggle GPU** (P100 / T4). Local RTX is not the training target.
