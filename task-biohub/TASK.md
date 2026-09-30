---
name: biohub-cell-tracking
task_type: optimization
metric: adjusted_edge_jaccard_plus_div
direction: maximize
---

# CZ Biohub — Cell Tracking During Development

Autonomous scientific agent optimization loop for **Rank 1 only** on the Kaggle leaderboard.

## Standing orders (Samer)
- Accept **nothing below Rank 1**.
- **Zero local download/train** — execution must use Kaggle cloud (`AUTOSCIENTISTS_EXEC_MODE=kaggle` / `kaggle_runner`).
- Local box = cockpit (hypotheses, FSM, kernel push/pull) only.
- **Kaggle submit only on a large jump** toward #1: expected Public **≥ 0.9750** (prefer **≥ 0.9765**). Tiny OOF wins → KEEP in ledger, **no competition submit**.

## Target Metric
- **Composite Score**: `adjusted_edge_jaccard + 0.1 * division_jaccard` (higher is better - maximize).
- `adjusted_edge_jaccard = max(0, edge_jaccard * (1.1 - 0.1 * (T_pred / T_true)))`.
- Internal FSM Champion anchor: **0.947 – 0.949** (Public baseline stack).
- Leader #1 ≈ **0.974** (Sergio Alvarez) — operational target **≥ 0.9765**.
- A result is **KEEP** if it strictly improves the AutoScientists champion metric **and** is on a path to Rank 1.
- Any modification causing leakage, regression in CV, or NaNs is recorded in the **Dead-End Ledger**.

## Search Space & Hypotheses
Hyperparameters and feature engineering flags passed via environment variables to `repo/train.py` (runs on **Kaggle**, not locally):
- `DETECTOR_BACKBONE`: `anisotropic_3d_unet`, `focus3d_stem`, `segresnet3d`
- `SUB_VOXEL_OFFSET`: `bounded_tanh` (max 0.86 um), `intensity_com`, `quadratic_taylor`
- `TRACKER_HEAD`: `local_line_graph_transformer` (k<=24), `hoct_att_rep`, `bilateral_top1`
- `TEMPORAL_WINDOW`: `T=5`, `T=8`
- `GAP_CLOSING`: `dt_max_2`, `dt_max_3`
- `MITOSIS_VERIFIER`: `lagrangian_comoving_itfi`, `pairwise_symmetric`
- `GRAPH_SOLVER`: `highs_ds_dual_simplex` (TUM flow), `lapjv_tracklet_stitch`
- `POST_PROCESSING`: `degree_zero_pruning` (Theorem 1), `energy_ranked_truncation`

## Data
- Competition data accessed **on Kaggle kernels** via competition/dataset sources (`biohub-cell-tracking-during-development`).
- External datasets: `royerlab/ultrack/zebrafish_embryo.ome.zarr/` (Zebrahub).
- Hardware for training: **Kaggle GPU** (P100 / T4). Local machine is control cockpit only.
