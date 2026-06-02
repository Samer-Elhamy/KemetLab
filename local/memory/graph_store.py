"""SQLite + NetworkX graph store for Graph-RAG."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import networkx as nx


class GraphStore:
    def __init__(self, focus_root: Path):
        self.focus_root = Path(focus_root)
        self.db_path = self.focus_root / "logs" / "graph.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.g = nx.DiGraph()
        self._conn = sqlite3.connect(self.db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                data JSON NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                kind TEXT NOT NULL,
                PRIMARY KEY (src, dst, kind)
            )
            """
        )
        self._conn.commit()
        self._load_into_networkx()

    def _load_into_networkx(self) -> None:
        self.g.clear()
        for nid, kind, data in self._conn.execute("SELECT id, kind, data FROM nodes"):
            self.g.add_node(nid, kind=kind, **json.loads(data))
        for src, dst, kind in self._conn.execute("SELECT src, dst, kind FROM edges"):
            self.g.add_edge(src, dst, kind=kind)

    def add_node(self, node_id: str, kind: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data)
        self._conn.execute(
            "INSERT OR REPLACE INTO nodes (id, kind, data) VALUES (?, ?, ?)",
            (node_id, kind, payload),
        )
        self.g.add_node(node_id, kind=kind, **data)
        self._conn.commit()

    def add_edge(self, src: str, dst: str, kind: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO edges (src, dst, kind) VALUES (?, ?, ?)",
            (src, dst, kind),
        )
        self.g.add_edge(src, dst, kind=kind)
        self._conn.commit()

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if node_id not in self.g:
            return None
        attrs = dict(self.g.nodes[node_id])
        kind = attrs.pop("kind", "unknown")
        return {"id": node_id, "kind": kind, **attrs}

    def nodes_by_kind(self, kind: str, limit: int = 20) -> list[dict[str, Any]]:
        out = []
        for nid, attrs in self.g.nodes(data=True):
            if attrs.get("kind") == kind:
                d = dict(attrs)
                d.pop("kind", None)
                out.append({"id": nid, **d})
                if len(out) >= limit:
                    break
        return out

    def neighbors(self, node_id: str, edge_kind: str | None = None) -> list[str]:
        if node_id not in self.g:
            return []
        result = []
        for _, dst, data in self.g.out_edges(node_id, data=True):
            if edge_kind is None or data.get("kind") == edge_kind:
                result.append(dst)
        return result

    def close(self) -> None:
        self._conn.close()
