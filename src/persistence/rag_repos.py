from __future__ import annotations

import json
from typing import Iterable, List, Optional

from .db import Database


class GlossaryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add_entry(
        self,
        term_src: str,
        lang_src: str,
        term_tgt: str,
        lang_tgt: str,
        notes: str | None = None,
    ) -> int:
        with self.db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO glossary_entries (term_src, lang_src, term_tgt, lang_tgt, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (term_src, lang_src, term_tgt, lang_tgt, notes),
            )
            return cursor.lastrowid

    def list_entries(
        self,
        lang_src: Optional[str] = None,
        lang_tgt: Optional[str] = None,
    ) -> List[dict]:
        conn = self.db.connect()
        cursor = conn.cursor()
        query = "SELECT * FROM glossary_entries"
        params: List[str] = []
        conditions: List[str] = []
        if lang_src:
            conditions.append("lang_src = ?")
            params.append(lang_src)
        if lang_tgt:
            conditions.append("lang_tgt = ?")
            params.append(lang_tgt)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


class CorpusRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add_snippet(
        self,
        text: str,
        language: str,
        tags: Iterable[str] | None = None,
        notes: str | None = None,
    ) -> int:
        tags_json = json.dumps([t.strip() for t in (tags or []) if t.strip()], ensure_ascii=False)
        with self.db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO corpus_snippets (text, language, tags, notes)
                VALUES (?, ?, ?, ?)
                """,
                (text, language, tags_json, notes),
            )
            return cursor.lastrowid

    def list_snippets(self, languages: Optional[List[str]] = None) -> List[dict]:
        conn = self.db.connect()
        cursor = conn.cursor()
        query = "SELECT * FROM corpus_snippets"
        params: List[str] = []
        if languages:
            placeholders = ",".join(["?"] * len(languages))
            query += f" WHERE language IN ({placeholders})"
            params.extend(languages)
        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        results: List[dict] = []
        for row in rows:
            record = dict(row)
            raw_tags = record.get("tags")
            if raw_tags:
                try:
                    record["tags"] = json.loads(raw_tags)
                except json.JSONDecodeError:
                    record["tags"] = []
            else:
                record["tags"] = []
            results.append(record)
        return results