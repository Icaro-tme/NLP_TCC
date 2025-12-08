from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        lang_src TEXT NOT NULL,
        lang_tgt TEXT NOT NULL,
        sha256 TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes (
        id INTEGER PRIMARY KEY,
        document_id INTEGER NOT NULL,
        node_path TEXT NOT NULL,
        tag TEXT,
        attrs TEXT,
        original_text TEXT NOT NULL,
        baseline_text TEXT,
        adapted_text TEXT,
        human_text TEXT,
        placeholders TEXT,
        status_adapted TEXT,
        status_human TEXT,
        context_text TEXT,
        FOREIGN KEY(document_id) REFERENCES documents(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS glossary_entries (
        id INTEGER PRIMARY KEY,
        term_src TEXT NOT NULL,
        lang_src TEXT NOT NULL,
        term_tgt TEXT NOT NULL,
        lang_tgt TEXT NOT NULL,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS corpus_snippets (
        id INTEGER PRIMARY KEY,
        text TEXT NOT NULL,
        language TEXT NOT NULL,
        tags TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
)


class Database:
    """Thin wrapper around sqlite3 connection lifecycle."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self.connection is None:
            self.connection = sqlite3.connect(
                self.db_path, 
                check_same_thread=False  # Permite uso em múltiplas threads (FastAPI/uvicorn)
            )
            self.connection.row_factory = sqlite3.Row
        return self.connection

    def init_schema(self) -> None:
        conn = self.connect()
        cursor = conn.cursor()
        for statement in SCHEMA_STATEMENTS:
            cursor.executescript(statement)
        conn.commit()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self.connect()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        finally:
            cursor.close()
