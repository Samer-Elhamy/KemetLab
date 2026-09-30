# task-profile.md — kaggle-s6e9

Local runtime profile for `task-kaggle-s6e9`. Used when `--runtime local` copies this file to `task-profile.md`.

---

## Hook: launch_command

```bash
python launch.py kaggle_run_v1 --task task-kaggle-s6e9 --runtime local
python local/orchestrator/runner.py --focus-root ../kaggle_run_v1 --max-cycles 5
```

---

## Hook: bootstrap_extras

Sets `RUNTIME=local`. Integrates with Kaggle 5-fold cross-validation and RTX 4050 GPU.

---

## Hook: discussion_policy

**Full FSM Multi-Agent Debate:** Proposer, Critic, Consensus Voter, and Code Synthesizer.

---

## Hook: seeding_policy

Orchestrator seeds initial Champion baseline: `roc_auc: 0.94293` (5-Fold LightGBM Baseline).

---

## Hook: gpu_dispatch

**Kaggle cloud GPU only** (`AUTOSCIENTISTS_EXEC_MODE=kaggle` / `local.orchestrator.kaggle_runner`).
Do **not** dispatch full training to the local RTX. Local machine is cockpit.

---

## Hook: champion_promotion

`local/orchestrator/promotion.py` writes `champion.json` if `roc_auc > current_champion`.
**Competition submit is separate:** only when expected Public ≥ **0.94703** (prefer ≥ **0.94720**) — Rank-1 bar, not tiny KEEP deltas.

---

## Hook: stagnation_response

After 3 consecutive DISCARDs, trigger Stagnation Recovery: diversify toward **public-anchor-beating** recipes (jazivxt/megayak/DGP-class), pseudo-label paths, and ensembles that can reach Rank 1 — not more weak 0.943 OOF variants.

---

## Hook: exit_condition

Stop / escalate when Rank-1 Public (≥ 0.94703) is achieved, or when ledger shows repeated dead-ends without a path past 0.94657 public anchors.

---
