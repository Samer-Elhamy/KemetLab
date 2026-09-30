# task-profile.md — meta-local

Local meta-improvement: agents patch the **experiments repo** and benchmark resource usage.

## Hook: launch_command

```bash
python launch.py meta_local_run --task task-meta-local --runtime local
```

## Hook: exit_condition

Stop when `resource_score` ≤ 50 **and** Ollama heavy+light both respond OK for 3 consecutive cycles, or user interrupt.

## Hook: bootstrap_extras

Set environment:

- `AUTOSCIENTISTS_TARGET_REPO` → experiments clone path
- `LOCAL_LLM_PROVIDER=ollama`
- `LOCAL_PROPOSE_MODE=llm` (agents must use Qwen for code proposals)
- Remove `LOCAL_PEER_REVIEW=local` so heavy Qwen reviews patches

## Hook: discussion_policy

Skip long discussion. One propose → review → benchmark per cycle.

## Hook: seeding_policy

First cycle: read `docs/META_LOCAL_RESEARCH.md` and propose one change to `ollama_client.py` or `retrieve.py`.
