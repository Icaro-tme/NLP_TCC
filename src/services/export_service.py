"""Service for exporting translated nodes back into HTML documents."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from ..core.placeholders import PlaceholderEncoder


class ExportService:
    """Reconstructs HTML variants from persisted node translations."""

    def __init__(self) -> None:
        self.placeholder_encoder = PlaceholderEncoder()

    def export_variant(
        self,
        original_html: str,
        nodes: Iterable[dict],
        variant: str,
        output_path: Path,
    ) -> None:
        """Write a reconstructed HTML file using the specified translation variant."""
        soup = BeautifulSoup(original_html, "html.parser")
        node_lookup = {node["node_path"]: node for node in nodes}
        for element in soup.find_all(attrs={"data-node-id": True}):
            node_path = element.get("data-node-id")
            node = node_lookup.get(node_path)
            if not node:
                continue
            text_value = node.get(f"{variant}_text") or node.get("original_text", "")
            element.clear()
            decoded_html = self.placeholder_encoder.decode_fragment(
                text_value, _deserialize_mapping(node.get("placeholders", {}))
            )
            # Parse the decoded HTML so inline tags are not escaped as text
            fragment = BeautifulSoup(decoded_html, "html.parser")
            for child in list(fragment.body.contents if fragment.body else fragment.contents):
                element.append(child)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str(soup), encoding="utf-8")


def _deserialize_mapping(mapping):  # type: ignore[override]
    from ..core.placeholders import PlaceholderSpec

    if isinstance(mapping, dict) and mapping and isinstance(next(iter(mapping.values())), PlaceholderSpec):
        return mapping
    deserialized = {}
    if isinstance(mapping, str):
        import json

        mapping = json.loads(mapping)
    if isinstance(mapping, dict):
        for token, payload in mapping.items():
            deserialized[token] = PlaceholderSpec(
                tag=payload.get("tag", "span"),
                attrs=payload.get("attrs", {}),
            )
    return deserialized
