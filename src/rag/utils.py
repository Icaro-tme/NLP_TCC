"""Utility helpers for managing RAG artefacts."""

from __future__ import annotations

from ..core.config import PathsConfig


def invalidate_rag_index(paths: PathsConfig) -> None:
    index_dir = paths.data_dir / "rag_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "rag_index.pkl"
    if index_file.exists():
        index_file.unlink()
