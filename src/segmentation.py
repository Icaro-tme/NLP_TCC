"""Segmentation and windowing helpers for improved translation context."""

from __future__ import annotations

from typing import Iterable, List, Tuple

SENTENCE_END = {".", "?", "!"}


def naive_sentence_split(text: str) -> List[str]:
    """Very lightweight sentence splitter (placeholder for nltk/spacy)."""
    parts: List[str] = []
    buff: List[str] = []
    for ch in text:
        buff.append(ch)
        if ch in SENTENCE_END:
            parts.append("".join(buff).strip())
            buff = []
    if buff:
        tail = "".join(buff).strip()
        if tail:
            parts.append(tail)
    return parts


def build_windows(nodes: Iterable[dict], max_chars: int = 800) -> List[Tuple[List[dict], str]]:
    """Group consecutive nodes into context windows respecting a char budget.

    Returns list of tuples: (list_of_nodes, concatenated_text_with_markers)
    """
    windows: List[Tuple[List[dict], str]] = []
    current_nodes: List[dict] = []
    current_text: List[str] = []
    current_len = 0
    for node in nodes:
        text = node.get("original_text", "")
        # Marker ensures we can split later.
        marker = f"<<<NODE:{node['id']}>>>"  # requires node has 'id'
        chunk = marker + "\n" + text + "\n"
        if current_len + len(chunk) > max_chars and current_nodes:
            windows.append((current_nodes[:], "".join(current_text)))
            current_nodes.clear()
            current_text.clear()
            current_len = 0
        current_nodes.append(node)
        current_text.append(chunk)
        current_len += len(chunk)
    if current_nodes:
        windows.append((current_nodes, "".join(current_text)))
    return windows


def split_window_translation(window_text: str) -> List[Tuple[str, str]]:
    """Split translated window back into (node_id, translated_text).

    Relies on marker lines surviving mostly intact; trims surrounding whitespace.
    """
    lines = window_text.splitlines()
    results: List[Tuple[str, str]] = []
    current_id: str | None = None
    buff: List[str] = []
    for line in lines:
        if line.startswith("<<<NODE:") and line.endswith(">>>"):
            # flush previous
            if current_id is not None:
                results.append((current_id, "\n".join(buff).strip()))
            current_id = line[len("<<<NODE:") : -3]
            buff = []
        else:
            buff.append(line)
    if current_id is not None:
        results.append((current_id, "\n".join(buff).strip()))
    return results
