"""Hybrid episodic memory system for autonomous trade compliance agent.

Provides:
1. Short-term working context: In-memory sliding window scratchpad.
2. Long-term audit trail: Persistent SQLite database recording queries, plans, tool calls, and decisions.
3. Semantic lookup: Cosine similarity vector search over past compliance episodes.
"""

from __future__ import annotations

import collections
import json
import math
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple


class TextVectorizer:
    """Lightweight in-memory vectorizer using subword/token frequency & cosine similarity."""

    def __init__(self) -> None:
        self.vocabulary: Dict[str, int] = {}
        self.doc_count: int = 0
        self.df: Dict[str, int] = collections.defaultdict(int)

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower())
        # Add character trigrams for robust fuzzy semantic matching
        trigrams = [text[i : i + 3].lower() for i in range(len(text) - 2) if " " not in text[i : i + 3]]
        return tokens + trigrams[:50]

    def fit_transform(self, documents: List[str]) -> List[List[float]]:
        self.vocabulary.clear()
        self.df.clear()
        self.doc_count = len(documents)

        all_doc_tokens: List[List[str]] = []
        for doc in documents:
            tokens = self._tokenize(doc)
            all_doc_tokens.append(tokens)
            unique_tokens = set(tokens)
            for t in unique_tokens:
                self.df[t] += 1
                if t not in self.vocabulary:
                    self.vocabulary[t] = len(self.vocabulary)

        vectors: List[List[float]] = []
        for tokens in all_doc_tokens:
            vectors.append(self._vectorize_tokens(tokens))
        return vectors

    def transform_single(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        return self._vectorize_tokens(tokens)

    def _vectorize_tokens(self, tokens: List[str]) -> List[float]:
        if not self.vocabulary:
            return []
        dim = len(self.vocabulary)
        vec = [0.0] * dim
        counts = collections.Counter(tokens)

        for t, count in counts.items():
            if t in self.vocabulary:
                idx = self.vocabulary[t]
                # TF-IDF weighting
                tf = count / max(1, len(tokens))
                idf = math.log((1 + self.doc_count) / (1 + self.df.get(t, 0))) + 1.0
                vec[idx] = tf * idf

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    return sum(a * b for a, b in zip(vec1, vec2))


class AgentEpisodicMemory:
    """
    Episodic & hybrid memory engine for Hermes compliance agent.
    Combines scratchpad, SQLite compliance journal, and semantic lookup.
    """

    def __init__(
        self,
        db_path: str = "lex_trade_memory.db",
        sliding_window_size: int = 12,
    ) -> None:
        self.db_path = db_path
        self.sliding_window_size = sliding_window_size
        self._scratchpad: List[Dict[str, Any]] = []
        self._vectorizer = TextVectorizer()
        self._episode_cache: List[Dict[str, Any]] = []

        # If in-memory, retain single connection across operations
        if self.db_path == ":memory:":
            self._shared_conn: Optional[sqlite3.Connection] = sqlite3.connect(":memory:")
        else:
            self._shared_conn = None

        self._init_sqlite_schema()
        self._warm_vector_index()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        return sqlite3.connect(self.db_path)

    def _init_sqlite_schema(self) -> None:
        """Create audit log & episode tables if they do not exist."""
        conn = self._get_connection()
        try:
            # Check for database/schema.sql
            schema_file = os.path.join(os.path.dirname(__file__), "../../database/schema.sql")
            if os.path.exists(schema_file):
                with open(schema_file, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
            else:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episodes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        shipment_id TEXT NOT NULL,
                        query_text TEXT NOT NULL,
                        action_plan TEXT,
                        tool_calls TEXT,
                        verdict TEXT,
                        risk_level TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        shipment_id TEXT NOT NULL,
                        step_name TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    )
                    """
                )
            conn.commit()
        finally:
            if self._shared_conn is None:
                conn.close()

    def _warm_vector_index(self) -> None:
        """Load stored episodes into vector space for quick similarity lookup."""
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes ORDER BY id DESC LIMIT 500")
            rows = cursor.fetchall()
        finally:
            if self._shared_conn is None:
                conn.close()

        self._episode_cache = []
        docs: List[str] = []
        for r in rows:
            ep = {
                "id": r["id"],
                "shipment_id": r["shipment_id"],
                "query_text": r["query_text"],
                "action_plan": json.loads(r["action_plan"] or "[]"),
                "tool_calls": json.loads(r["tool_calls"] or "[]"),
                "verdict": json.loads(r["verdict"] or "{}"),
                "risk_level": r["risk_level"],
                "created_at": r["created_at"],
            }
            self._episode_cache.append(ep)
            docs.append(f"{ep['query_text']} {ep['risk_level']} {json.dumps(ep['verdict'])}")

        if docs:
            vectors = self._vectorizer.fit_transform(docs)
            for i, vec in enumerate(vectors):
                self._episode_cache[i]["vector"] = vec

    # ========================================================================
    # Short-Term Working Scratchpad
    # ========================================================================

    def add_scratchpad_message(
        self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Append message to working sliding window context."""
        entry = {
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._scratchpad.append(entry)
        if len(self._scratchpad) > self.sliding_window_size:
            self._scratchpad = self._scratchpad[-self.sliding_window_size :]

    def get_scratchpad(self) -> List[Dict[str, Any]]:
        """Retrieve recent scratchpad messages."""
        return list(self._scratchpad)

    def clear_scratchpad(self) -> None:
        """Clear scratchpad working context."""
        self._scratchpad.clear()

    # ========================================================================
    # Long-Term Episodic Recording & Audit Logging
    # ========================================================================

    def record_audit_step(self, shipment_id: str, step_name: str, payload: Any) -> None:
        """Persist compliance audit trace step."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_logs (shipment_id, step_name, payload, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (shipment_id, step_name, json.dumps(payload), time.time()),
            )
            conn.commit()
        finally:
            if self._shared_conn is None:
                conn.close()

    def record_episode(
        self,
        shipment_id: str,
        query_text: str,
        action_plan: List[str],
        tool_calls: List[Dict[str, Any]],
        verdict: Dict[str, Any],
        risk_level: str,
    ) -> int:
        """Store completed decision episode in SQLite and vector space."""
        now = time.time()
        plan_json = json.dumps(action_plan)
        tools_json = json.dumps(tool_calls)
        verdict_json = json.dumps(verdict)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO episodes (shipment_id, query_text, action_plan, tool_calls, verdict, risk_level, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (shipment_id, query_text, plan_json, tools_json, verdict_json, risk_level, now),
            )
            episode_id = cursor.lastrowid or 0
            conn.commit()
        finally:
            if self._shared_conn is None:
                conn.close()

        # Update cache & re-index
        episode_data = {
            "id": episode_id,
            "shipment_id": shipment_id,
            "query_text": query_text,
            "action_plan": action_plan,
            "tool_calls": tool_calls,
            "verdict": verdict,
            "risk_level": risk_level,
            "created_at": now,
        }
        self._episode_cache.append(episode_data)

        # Refresh vectorizer representation
        docs = [
            f"{e['query_text']} {e['risk_level']} {json.dumps(e['verdict'])}"
            for e in self._episode_cache
        ]
        vectors = self._vectorizer.fit_transform(docs)
        for i, vec in enumerate(vectors):
            self._episode_cache[i]["vector"] = vec

        return episode_id

    # ========================================================================
    # Semantic Retrieval
    # ========================================================================

    def search_episodes(
        self, query_text: str, top_k: int = 3, min_similarity: float = 0.15
    ) -> List[Dict[str, Any]]:
        """
        Search past episodes using cosine similarity over query tokens and concepts.
        Helps reuse past precedents for recurring classifications.
        """
        if not self._episode_cache or not self._vectorizer.vocabulary:
            return []

        query_vec = self._vectorizer.transform_single(query_text)
        scored: List[Tuple[float, Dict[str, Any]]] = []

        for ep in self._episode_cache:
            ep_vec = ep.get("vector")
            if ep_vec:
                sim = cosine_similarity(query_vec, ep_vec)
                if sim >= min_similarity:
                    scored.append((sim, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: List[Dict[str, Any]] = []
        for sim, ep in scored[:top_k]:
            item = dict(ep)
            item["similarity"] = round(sim, 4)
            item.pop("vector", None)
            results.append(item)

        return results

    def get_audit_trail(self, shipment_id: str) -> List[Dict[str, Any]]:
        """Retrieve audit log history for a specific shipment."""
        conn = self._get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audit_logs WHERE shipment_id = ? ORDER BY timestamp ASC",
                (shipment_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": r["id"],
                    "shipment_id": r["shipment_id"],
                    "step_name": r["step_name"],
                    "payload": json.loads(r["payload"]),
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]
        finally:
            if self._shared_conn is None:
                conn.close()
