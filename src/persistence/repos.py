"""Repository layer encapsulating raw SQL queries."""

from __future__ import annotations

import json
from typing import Iterable, List, Optional

from .db import Database


class DocumentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_document(
        self, name: str, lang_src: str, lang_tgt: str, sha256: str | None
    ) -> int:
        with self.db.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM documents WHERE name = ? AND lang_src = ? AND lang_tgt = ?",
                (name, lang_src, lang_tgt),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE documents SET sha256 = ? WHERE id = ?",
                    (sha256, row["id"]),
                )
                return row["id"]
            cursor.execute(
                "INSERT INTO documents (name, lang_src, lang_tgt, sha256) VALUES (?, ?, ?, ?)",
                (name, lang_src, lang_tgt, sha256),
            )
            return cursor.lastrowid

    def get_document(self, document_id: int) -> Optional[dict]:
        connection = self.db.connect()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def find_document_id(self, name: str, lang_src: str, lang_tgt: str) -> Optional[int]:
        connection = self.db.connect()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM documents WHERE name = ? AND lang_src = ? AND lang_tgt = ?",
            (name, lang_src, lang_tgt),
        )
        row = cursor.fetchone()
        return row["id"] if row else None


class NodeRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_nodes(self, document_id: int, nodes: Iterable[dict]) -> None:
        with self.db.cursor() as cursor:
            for node in nodes:
                cursor.execute(
                    """
                    INSERT INTO nodes (
                        document_id, node_path, tag, attrs, original_text,
                        placeholders, status_adapted, status_human
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        node["node_path"],
                        node.get("tag"),
                        json.dumps(node.get("attrs", {}), ensure_ascii=False),
                        node.get("original_text", ""),
                        json.dumps(node.get("placeholders", {}), ensure_ascii=False),
                        "pending",
                        "none",
                    ),
                )

    def delete_nodes_by_document(self, document_id: int) -> None:
        with self.db.cursor() as cursor:
            cursor.execute("DELETE FROM nodes WHERE document_id = ?", (document_id,))

    def save_translation(self, node_id: int, translation: str) -> None:
        """Persiste a tradução gerada em todas as colunas relevantes."""
        with self.db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE nodes SET
                    baseline_text = ?,
                    adapted_text = ?,
                    context_text = '',
                    status_adapted = 'fresh'
                WHERE id = ?
                """,
                (translation, translation, node_id),
            )

    def mark_stale_by_document(self, document_id: int) -> None:
        with self.db.cursor() as cursor:
            cursor.execute(
                "UPDATE nodes SET status_adapted = 'stale' WHERE document_id = ?",
                (document_id,),
            )

    def list_nodes(self, document_id: int) -> List[dict]:
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM nodes WHERE document_id = ? ORDER BY node_path",
            (document_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


