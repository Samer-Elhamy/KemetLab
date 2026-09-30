# Meta-Local Research Brief (for AutoScientists agents)

References and techniques for **local-only** dual-Qwen operation on ~6GB VRAM / 8–16GB RAM.
Agents may cite and implement ideas below in the **experiments repo** only.

## 1. Dual-model routing (Qwen heavy + light)

| Technique | Source / idea | Application |
|-----------|---------------|-------------|
| **FrugalGPT-style cascade** | Chen et al., FrugalGPT | Route easy FSM states to light model; escalate on validation failure |
| **RouteLLM** | Ong et al. | Score prompt difficulty (`local/llm/difficulty.py`) — already present; tune thresholds |
| **Speculative drafting** | Leviathan et al. | Light model drafts JSON; heavy verifies only on schema fail |

**Local config:** `local/config/routing.yaml` — set `heavy` to largest Qwen that fits (e.g. `qwen3.5:0.8b` or custom GGUF), `light` to smallest (`qwen3.5:0.8b` or 0.5B class).

## 2. VRAM / RAM reduction (Ollama)

| Technique | Notes |
|-----------|--------|
| `keep_alive: 0` after each call | Already in `unload_model_from_vram()` — ensure non-blocking |
| `num_ctx` 1024–2048 for light tier | Cuts KV cache ~linearly |
| `num_gpu` / layer offload | `OLLAMA_NUM_GPU` env; partial GPU + CPU spill |
| **Q4_K_M / Q4_K_XL** quant | Smaller weights; slight quality loss OK per user |
| Sequential LLM calls | Never parallel Ollama loads on 6GB |

Papers: **LLM.int8()**, **GPTQ** (quantization surveys 2023–2024).

## 3. Token / prompt economy

| Technique | File targets |
|-----------|--------------|
| Anchor + skip-connection prompts | `local/memory/retrieve.py` — trim BlockSummary count |
| **LLMLingua / LongLLMLingua** | Compress graph context before Qwen heavy |
| Shorter system prompts | `local/prompts/*.txt` |
| **orjson** | Faster JSON in graph ingest |

## 4. Data & memory (Graph-RAG)

| Technique | Application |
|-----------|-------------|
| SQLite WAL + indexes | `local/memory/graph_store.py` |
| **NetworkX** only for hot path subset | Limit `k_nodes`, `k_blocks` |
| Block summaries instead of raw shards | Already in blocks.py — increase synthesis frequency |
| **Chroma / sqlite-vec** (optional external) | Semantic retrieval instead of full graph scan — slight recall loss OK |

## 5. I/O latency

| Technique | File |
|-----------|------|
| `requests.Session()` pool | `local/llm/ollama_client.py` |
| Async unload | `asyncio` thread for keep_alive=0 |
| Pre-fetch graph while training | `local/orchestrator/runner.py` pipeline |

## 6. Acceptable tradeoffs (user policy)

- **Slight accuracy drop** in peer review or proposal quality: OK if `resource_score` drops ≥5%
- **Longer wall-clock** per cycle: OK if usable (<10 min/cycle target on laptop)
- **Skip cloud entirely**: `LOCAL_LLM_PROVIDER=ollama` only

## 7. Success criteria (meta task)

- `resource_score` ≤ 50 with both heavy and light Ollama responding
- One full smoke FSM cycle completes without OpenRouter
- Production dashboard can switch to experiments repo when champion meta score stable 3 cycles

## External tools (optional, not required)

- **LiteLLM** — unified router (if abandoning custom client)
- **LangGraph** — FSM visualization only
- **Weights & Biases** — overkill; use `logs/autorun.jsonl` instead

---

*Cursor bootstrap note: this file is read-only guidance for agents; implement patches in `AUTOSCIENTISTS_TARGET_REPO`.*
