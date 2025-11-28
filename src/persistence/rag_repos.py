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

    def update_entry(
        self,
        entry_id: int,
        term_src: Optional[str] = None,
        lang_src: Optional[str] = None,
        term_tgt: Optional[str] = None,
        lang_tgt: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        fields = []
        params: List[str] = []
        if term_src is not None:
            fields.append("term_src = ?")
            params.append(term_src)
        if lang_src is not None:
            fields.append("lang_src = ?")
            params.append(lang_src)
        if term_tgt is not None:
            fields.append("term_tgt = ?")
            params.append(term_tgt)
        if lang_tgt is not None:
            fields.append("lang_tgt = ?")
            params.append(lang_tgt)
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)
        if not fields:
            return False
        with self.db.cursor() as cursor:
            cursor.execute(
                f"UPDATE glossary_entries SET {', '.join(fields)} WHERE id = ?",
                (*params, entry_id),
            )
            return cursor.rowcount > 0

    def delete_entry(self, entry_id: int) -> bool:
        with self.db.cursor() as cursor:
            cursor.execute("DELETE FROM glossary_entries WHERE id = ?", (entry_id,))
            return cursor.rowcount > 0


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

    def update_snippet(
        self,
        snippet_id: int,
        text: Optional[str] = None,
        language: Optional[str] = None,
        tags: Iterable[str] | None = None,
        notes: Optional[str] = None,
    ) -> bool:
        fields = []
        params: List[str] = []
        if text is not None:
            fields.append("text = ?")
            params.append(text)
        if language is not None:
            fields.append("language = ?")
            params.append(language)
        if tags is not None:
            fields.append("tags = ?")
            params.append(json.dumps([t.strip() for t in tags if t.strip()], ensure_ascii=False))
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)
        if not fields:
            return False
        with self.db.cursor() as cursor:
            cursor.execute(
                f"UPDATE corpus_snippets SET {', '.join(fields)} WHERE id = ?",
                (*params, snippet_id),
            )
            return cursor.rowcount > 0

    def delete_snippet(self, snippet_id: int) -> bool:
        with self.db.cursor() as cursor:
            cursor.execute("DELETE FROM corpus_snippets WHERE id = ?", (snippet_id,))
            return cursor.rowcount > 0