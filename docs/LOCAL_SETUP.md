# Local AutoScientists Setup

**Claude and ClawInstitute are not used.** All LLM work goes through **`qwen35custom`** (Ollama) with automatic **difficulty-based** routing:

- **Heavy (9B):** complex propose / review
- **Light (0.8B):** repair, summaries, small prompts

Offline runtime for consumer hardware (**6–8GB VRAM**, **8–16GB RAM**).

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.com/) (optional for live inference; use mock mode for CI)
- Node.js 22+ only if using ClawInstitute (`--runtime claude`)

## Install

```bash
cd AutoScientists-Local
pip install -r requirements.txt
```

## Pull models (Ollama)

```bash
ollama pull qwen3.5-9b-gguf:ud-q4_k_xl
ollama pull qwen3.5:0.8b-gguf
```

Create a unified gateway Modelfile (example):

```dockerfile
# Modelfile name: qwen35custom
FROM qwen3.5-9b-gguf:ud-q4_k_xl
```

Register with: `ollama create qwen35custom -f Modelfile`

Tier routing is handled in Python (`local/llm/qwen35custom.py`); the gateway name is the default API target.

## Launch smoke experiment

```bash
python launch.py smoke_v1 --task task-smoke-local --run --cycles 1
```

## Run one FSM iteration

With Ollama running:

```bash
python local/orchestrator/runner.py --focus-root ../smoke_v1 --max-cycles 1
```

Without Ollama (mock LLM for tests):

```bash
# Windows PowerShell
$env:LOCAL_MOCK_LLM="1"
python local/orchestrator/runner.py --focus-root ../smoke_v1 --max-cycles 1
```

## Success criteria

- Log: `[FSM] state=UpdateGraph complete`
- `logs/experiments.jsonl` has a KEEP or DISCARD entry
- `champion.json` updated on improvement
- Prompt budget: ≤4096 tokens input per LLM call

## VRAM notes

1. Tier-1 (9B Q4) and Tier-2 (0.8B) never load simultaneously.
2. `unload_model_from_vram()` runs before `train.py`.
3. Use `LOCAL_MOCK_LLM=1` to validate orchestration without GPU inference.
