# task-profile.md — smoke-local

Local runtime profile for `task-smoke-local`. Used when `--runtime local` copies this file to `task-profile.md`.

---

## Hook: launch_command

```bash
python launch.py <run-name> --task task-smoke-local --runtime local
python local/orchestrator/runner.py --focus-root <run-dir> --max-cycles 1
```

---

## Hook: bootstrap_extras

Sets `RUNTIME=local`. No ClawInstitute workshop required for smoke runs.

---

## Hook: discussion_policy

**Skipped.** Fixed single-team roster seeded by `launch_local.py`.

---

## Hook: seeding_policy

Orchestrator seeds one default proposal in graph store on first cycle.

---

## Hook: gpu_dispatch

N/A — local runner uses sequential FSM; one train subprocess per cycle.

---

## Hook: champion_promotion

`local/orchestrator/promotion.py` writes `champion.json` and copies best `train.py` to `champion/`.

---

## Hook: stagnation_response

After 3 consecutive DISCARDs, log warning and continue (smoke default).

---

## Hook: exit_condition

Returns True when `--max-cycles` completed.

---

## Hook: final_report

Print champion `val_loss` and experiment log path.

---

## Hook: pre_cycle_check

No-op (returns False).

---

## Hook: periodic_hooks

No-op.

---

## Hook: analyst_prompt_extras

Empty.

---

## Hook: never_do_extras

Do not call Claude Code or cloud LLM APIs in local runtime.
