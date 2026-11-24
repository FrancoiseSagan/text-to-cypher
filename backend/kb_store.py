"""SQLite store for NL-Cypher Knowledge Base (CRUD + hybrid semantic retrieval) & Query Trace History."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from .config import settings
from .models import KBItem, KBItemCreate, KBItemUpdate


def _tokenize(text: str) -> list[str]:
    """Mixed Chinese character bigram + English/code identifier tokenizer for fast local semantic similarity."""
    text_l = text.lower()
    en_tokens = re.findall(r"[a-z0-9_-]{2,}", text_l)
    zh_chars = re.findall(r"[\u4e00-\u9fff]", text_l)
    zh_bigrams = [zh_chars[i] + zh_chars[i + 1] for i in range(len(zh_chars) - 1)]
    return en_tokens * 2 + zh_chars + zh_bigrams * 2


class KBStore:
    def __init__(self, db_path: Path | None = None, seed_path: Path | None = None):
        self.db_path = db_path or settings.sqlite_path
        self.seed_path = seed_path or settings.seed_kb_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_if_empty()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_items (
                    id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    cypher TEXT NOT NULL,
                    category TEXT NOT NULL,
                    complexity TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    description TEXT NOT NULL DEFAULT '',
                    verified INTEGER NOT NULL DEFAULT 1,
                    last_row_count INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_history (
                    query_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    intent_category TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cypher TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    total_duration_ms REAL NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM kb_items").fetchone()[0]
            if cnt > 0 or not self.seed_path.exists():
                return
            items = json.loads(self.seed_path.read_text(encoding="utf-8"))
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            for it in items:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO kb_items
                    (id, question, cypher, category, complexity, tags, description, verified, last_row_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)
                    """,
                    (
                        it.get("id") or f"kb-{uuid.uuid4().hex[:8]}",
                        it["question"],
                        it["cypher"],
                        it["category"],
                        it.get("complexity", "简单"),
                        json.dumps(it.get("tags", []), ensure_ascii=False),
                        it.get("description", ""),
                        now,
                        now,
                    ),
                )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> KBItem:
        return KBItem(
            id=row["id"],
            question=row["question"],
            cypher=row["cypher"],
            category=row["category"],
            complexity=row["complexity"],
            tags=json.loads(row["tags"] or "[]"),
            description=row["description"] or "",
            verified=bool(row["verified"]),
            last_row_count=row["last_row_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_items(self, keyword: str = "", category: str = "", complexity: str = "") -> list[KBItem]:
        clauses: list[str] = []
        params: list[Any] = []
        if category and category != "全部":
            clauses.append("category = ?")
            params.append(category)
        if complexity and complexity != "全部":
            clauses.append("complexity = ?")
            params.append(complexity)
        if keyword.strip():
            kw = f"%{keyword.strip()}%"
            clauses.append("(question LIKE ? OR cypher LIKE ? OR tags LIKE ? OR description LIKE ?)")
            params.extend([kw, kw, kw, kw])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM kb_items {where} ORDER BY id ASC", params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_categories(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) AS count FROM kb_items GROUP BY category ORDER BY count DESC, category ASC"
            ).fetchall()
        return [{"category": r["category"], "count": r["count"]} for r in rows]

    def get_item(self, item_id: str) -> KBItem | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM kb_items WHERE id = ?", (item_id,)).fetchone()
        return self._row_to_item(row) if row else None

    def create_item(self, data: KBItemCreate, verified: bool = True, last_row_count: int | None = None) -> KBItem:
        item_id = f"kb-{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kb_items
                (id, question, cypher, category, complexity, tags, description, verified, last_row_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    data.question.strip(),
                    data.cypher.strip(),
                    data.category.strip(),
                    data.complexity,
                    json.dumps(data.tags, ensure_ascii=False),
                    data.description.strip(),
                    1 if verified else 0,
                    last_row_count,
                    now,
                    now,
                ),
            )
        return self.get_item(item_id)  # type: ignore[return-value]

    def update_item(self, item_id: str, data: KBItemUpdate, verified: bool | None = None, last_row_count: int | None = None) -> KBItem | None:
        existing = self.get_item(item_id)
        if not existing:
            return None
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        new_q = data.question.strip() if data.question is not None else existing.question
        new_c = data.cypher.strip() if data.cypher is not None else existing.cypher
        new_cat = data.category.strip() if data.category is not None else existing.category
        new_comp = data.complexity if data.complexity is not None else existing.complexity
        new_tags = data.tags if data.tags is not None else existing.tags
        new_desc = data.description.strip() if data.description is not None else existing.description
        new_ver = existing.verified if verified is None else verified
        new_cnt = existing.last_row_count if last_row_count is None else last_row_count

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE kb_items
                SET question=?, cypher=?, category=?, complexity=?, tags=?, description=?, verified=?, last_row_count=?, updated_at=?
                WHERE id=?
                """,
                (
                    new_q,
                    new_c,
                    new_cat,
                    new_comp,
                    json.dumps(new_tags, ensure_ascii=False),
                    new_desc,
                    1 if new_ver else 0,
                    new_cnt,
                    now,
                    item_id,
                ),
            )
        return self.get_item(item_id)

    def delete_item(self, item_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM kb_items WHERE id = ?", (item_id,))
        return cur.rowcount > 0

    def retrieve_similar(self, query: str, top_k: int = 4, intent_category: str = "") -> list[dict[str, Any]]:
        """TF-IDF weighted cosine similarity retrieval with intent category boost."""
        items = self.list_items()
        if not items:
            return []

        docs = [
            _tokenize(f"{it.question} {it.category} {' '.join(it.tags)} {it.description}")
            for it in items
        ]
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        # Compute IDF across KB corpus
        n_docs = len(docs)
        df: Counter[str] = Counter()
        for tok_list in docs:
            for t in set(tok_list):
                df[t] += 1

        def _tfidf_vec(tok_list: list[str]) -> dict[str, float]:
            tf = Counter(tok_list)
            return {t: cnt * (math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0) for t, cnt in tf.items()}

        q_vec = _tfidf_vec(q_tokens)
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        scored: list[tuple[float, KBItem]] = []
        for it, d_toks in zip(items, docs):
            d_vec = _tfidf_vec(d_toks)
            d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1.0
            dot = sum(q_vec[t] * d_vec.get(t, 0.0) for t in q_vec)
            sim = dot / (q_norm * d_norm)
            if intent_category and it.category == intent_category:
                sim += 0.15
            scored.append((round(sim, 4), it))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": it.id,
                "question": it.question,
                "cypher": it.cypher,
                "category": it.category,
                "complexity": it.complexity,
                "score": score,
            }
            for score, it in scored[:top_k]
        ]

    # --- Query History & Trace Persistence ---
    def save_history(self, response_dict: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO query_history
                (query_id, question, difficulty, intent_category, provider, model, status, cypher, row_count, total_duration_ms, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_dict["query_id"],
                    response_dict["question"],
                    response_dict.get("resolved_difficulty", ""),
                    response_dict.get("intent_category", ""),
                    response_dict.get("provider", ""),
                    response_dict.get("model", ""),
                    response_dict.get("status", "error"),
                    response_dict.get("cypher", ""),
                    response_dict.get("row_count", 0),
                    response_dict.get("total_duration_ms", 0.0),
                    json.dumps(response_dict, ensure_ascii=False),
                    response_dict.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")),
                ),
            )

    def list_history(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT query_id, question, difficulty, intent_category, provider, model, status, cypher, row_count, total_duration_ms, created_at
                FROM query_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_history_item(self, query_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM query_history WHERE query_id = ?", (query_id,)).fetchone()
        return json.loads(row["payload_json"]) if row else None


kb_store = KBStore()
