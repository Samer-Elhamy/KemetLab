#!/usr/bin/env python3
"""Minimal smoke training script — prints val_loss JSON to stdout."""

import json
import os
import random
import sys

try:
    import torch
    import torch.nn as nn
except ImportError:
    torch = None


def _train_torch(lr: float, hidden: int, steps: int) -> float:
    torch.manual_seed(42)
    x = torch.randn(128, 8)
    y = torch.randn(128, 1)
    model = nn.Sequential(nn.Linear(8, hidden), nn.ReLU(), nn.Linear(hidden, 1))
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    for _ in range(steps):
        opt.zero_grad()
        pred = model(x)
        loss = loss_fn(pred, y)
        loss.backward()
        opt.step()
    with torch.no_grad():
        return float(loss_fn(model(x), y).item())


def _train_numpy(lr: float, hidden: int, steps: int) -> float:
    random.seed(42)
    # Synthetic scalar loss decreases with lower lr and more steps
    base = 1.0 / (1.0 + steps * lr * 10)
    noise = random.uniform(-0.02, 0.02)
    return max(0.01, base + noise + hidden * 1e-5)


def main() -> None:
    lr = float(os.environ.get("SMOKE_LR", "0.05"))
    hidden = int(os.environ.get("SMOKE_HIDDEN", "16"))
    steps = int(os.environ.get("SMOKE_STEPS", "30"))

    if torch is not None:
        val_loss = _train_torch(lr, hidden, steps)
    else:
        val_loss = _train_numpy(lr, hidden, steps)

    out = {
        "val_loss": val_loss,
        "exp_id": os.environ.get("SMOKE_EXP_ID", "smoke_run"),
        "params": {"lr": lr, "hidden_dim": hidden, "steps": steps},
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
