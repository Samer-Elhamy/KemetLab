---
name: smoke-local
task_type: optimization
metric: val_loss
direction: minimize
---

# Smoke Local Task

Fast deterministic training loop for validating the local AutoScientists runtime.

## Metric

- **val_loss**: lower is better (minimize).
- A result is **KEEP** if it strictly improves the champion `val_loss`.

## Search space

Hyperparameters passed via environment variables to `repo/train.py`:

| Parameter | Range |
|-----------|-------|
| `lr` | 0.001 – 0.1 |
| `hidden_dim` | 8 – 128 |
| `steps` | 10 – 100 |

## Hardware

Runs on CPU by default; optional CUDA if available. Designed for 6–8GB VRAM machines when GPU is used for Ollama only.

## Run

```bash
python launch.py smoke_v1 --task task-smoke-local --runtime local
python local/orchestrator/runner.py --focus-root ../smoke_v1 --max-cycles 1
```
