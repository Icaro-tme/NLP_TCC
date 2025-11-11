"""File-system helpers for HTML ingestion and export."""

from __future__ import annotations

from pathlib import Path


def read_html(path: Path) -> str:
    """Load HTML content from disk, ensuring UTF-8 decoding."""
    return path.read_text(encoding="utf-8")


def write_html(path: Path, html: str) -> None:
    """Persist HTML content to disk (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
