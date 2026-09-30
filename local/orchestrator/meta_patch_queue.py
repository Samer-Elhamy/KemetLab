"""Research-backed patch queue when Ollama/Qwen is offline — agents consume one per cycle."""

from __future__ import annotations

from typing import Any

# Each entry is a valid meta_proposal shape (path relative to experiments repo)
PATCH_QUEUE: list[dict[str, Any]] = [
    {
        "hypothesis": "Connection pooling reduces Ollama HTTP overhead (FrugalGPT I/O pillar)",
        "changes": [
            {
                "path": "local/llm/ollama_client.py",
                "search": "import requests\n\nfrom local.llm import qwen35custom",
                "replace": "import requests\n\nfrom local.llm import qwen35custom\n\n_SESSION: requests.Session | None = None\n\n\ndef _http() -> requests.Session:\n    global _SESSION\n    if _SESSION is None:\n        _SESSION = requests.Session()\n    return _SESSION\n",
            },
            {
                "path": "local/llm/ollama_client.py",
                "search": "response = requests.post(OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT)",
                "replace": "response = _http().post(OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT)",
            },
        ],
        "rationale": "Reuse TCP connections across FSM turns",
        "tier_hint": "both",
        "source": "research_queue",
    },
    {
        "hypothesis": "Lower default num_ctx cuts KV RAM (~linear)",
        "changes": [
            {
                "path": "local/llm/ollama_client.py",
                "search": 'NUM_CTX = int(os.environ.get("LOCAL_OLLAMA_NUM_CTX", "2048"))',
                "replace": 'NUM_CTX = int(os.environ.get("LOCAL_OLLAMA_NUM_CTX", "1536"))',
            }
        ],
        "rationale": "1536 ctx default for 6GB laptops",
        "tier_hint": "light",
        "source": "research_queue",
    },
    {
        "hypothesis": "Trim graph context tokens in retrieve.py",
        "changes": [
            {
                "path": "local/memory/retrieve.py",
                "search": "def global_context(graph: GraphStore, k_blocks: int = 3, k_nodes: int = 8)",
                "replace": "def global_context(graph: GraphStore, k_blocks: int = 2, k_nodes: 5)",
            }
        ],
        "rationale": "Smaller RAG payload → faster light/heavy calls",
        "tier_hint": "both",
        "source": "research_queue",
    },
]


def pick_patch(cycle: int) -> dict[str, Any]:
    if not PATCH_QUEUE:
        return {
            "status": "error",
            "reason": "patch queue empty",
        }
    return dict(PATCH_QUEUE[(cycle - 1) % len(PATCH_QUEUE)])
