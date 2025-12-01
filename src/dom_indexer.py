"""DOM indexing utilities that extract text nodes with stable identifiers."""

from __future__ import annotations

from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from .core.placeholders import PlaceholderEncoder, PlaceholderSpec

BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "td", "th", "caption"}
SKIP_TAGS = {"script", "style"}


def index_html(html: str, ids_map: Optional[Dict[str, int]] = None) -> tuple[str, List[dict]]:
    """Retorna HTML com atributos `data-node-id` e metadados dos nós.

    Quando `ids_map` é fornecido (node_path -> id de banco), também insere
    `data-node-database-id` diretamente na tag do nó correspondente.
    """
    soup = BeautifulSoup(html, "html.parser")
    nodes: List[dict] = []
    _walk_children(soup.body or soup, prefix="", nodes=nodes, ids_map=ids_map or {})
    return str(soup), nodes


def _walk_children(parent: Tag | BeautifulSoup, prefix: str, nodes: List[dict], ids_map: Dict[str, int]) -> None:
    child_index = 0
    for child in parent.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            continue
        tag_name = child.name.lower()
        if tag_name in SKIP_TAGS:
            child.decompose()
            continue
        node_path = f"{prefix}.{child_index}" if prefix else str(child_index)
        if tag_name in BLOCK_TAGS:
            encoder = PlaceholderEncoder()
            fragment = child.decode_contents()
            encoded_text, mapping = encoder.encode_fragment(fragment)
            child.attrs["data-node-id"] = node_path
            # Se já existe id de banco para este path, inserir no HTML
            db_id = ids_map.get(node_path)
            if db_id is not None:
                child.attrs["data-node-database-id"] = str(db_id)
            nodes.append(
                {
                    "node_path": node_path,
                    "tag": tag_name,
                    "attrs": dict(child.attrs),
                    "original_text": encoded_text,
                    "placeholders": _serialize_mapping(mapping),
                }
            )
        _walk_children(child, node_path, nodes, ids_map)
        child_index += 1


def _serialize_mapping(mapping: Dict[str, PlaceholderSpec]) -> Dict[str, dict]:
    return {
        token: {"tag": spec.tag, "attrs": spec.attrs}
        for token, spec in mapping.items()
    }
