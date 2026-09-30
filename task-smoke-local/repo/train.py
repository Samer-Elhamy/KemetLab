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


def _resolve_device() -> "torch.device":
    pref = os.environ.get("SMOKE_DEVICE", "auto").lower()
    if pref == "cpu":
        return torch.device("cpu")
    if pref == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    if pref == "auto" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _train_torch(lr: float, hidden: int, steps: int) -> float:
    device = _resolve_device()
    torch.manual_seed(42)
    if device.type == "cuda":
        torch.cuda.manual_seed(42)
    x = torch.randn(128, 8, device=device)
    y = torch.randn(128, 1, device=device)
    model = nn.Sequential(nn.Linear(8, hidden), nn.ReLU(), nn.Linear(hidden, 1)).to(device)
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

    device_name = "cpu"
    if torch is not None:
        device_name = str(_resolve_device())
    out = {
        "val_loss": val_loss,
        "exp_id": os.environ.get("SMOKE_EXP_ID", "smoke_run"),
        "params": {"lr": lr, "hidden_dim": hidden, "steps": steps},
        "device": device_name,
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
