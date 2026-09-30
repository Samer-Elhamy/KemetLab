---
name: hyperspectral-detection
task_type: optimization
metric: map50_95
direction: maximize
---

# Hyperspectral Object Detection Challenge 2026

Autonomous Rank-1 loop — **single-model only**.

## Standing orders (Samer)
- Accept **nothing below Rank 1**.
- **Zero local download/train** of competition dump; train only on **Kaggle GPU kernels**.
- **Competition rules (official):**
  - Only a **single detection model** — ensembles / WBF / multi-model fusion **banned**.
  - Undeclared external pre-training **banned** → prefer **from-scratch** (no COCO warmstart for prize path).
- Expert recipe (`piririp/approach-2`): YOLO11L-P2, `channels:16`, demosaic cubes, **250 epochs**, `patience=300`, `imgsz=1280`, `conf=0.001`, no TTA.
- **Submit only on a large jump:** expected Public **≥ 0.62** (first big leap), then **≥ 0.70** to take #1. Do not submit for +ε over `0.53758`.

## Standing
- Best Public: **0.53758** (RGB PNG Autoscientists).
- Rank 1 Public: **0.68006** (2026-09-21).
- Cloud RUNNING: `hyper-yolo11l-p2-16ch-train` (120ep), `hyper-yolo11l-p2-warmstart-train` (risky under rules).
- Ready to push when GPU free: `hyper-yolo11l-p2-16ch-250ep` (Piririp-exact).

## Target Metric
- **map50_95** maximize; operational #1 clear at **≥ 0.70**.
