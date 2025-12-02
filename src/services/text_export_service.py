"""Serviço de exportação em texto plano das traduções dos nós.

Preserva a ordem lógica dos nós do documento e decodifica placeholders para
recuperar marcas inline.

Regra especial: para variante "adapted" prioriza `human_text` quando existir,
permitindo que correções humanas sejam refletidas na saída adaptada sem
alterar a baseline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from ..core.placeholders import PlaceholderEncoder


class TextExportService:
    def __init__(self) -> None:
        self.placeholder_encoder = PlaceholderEncoder()

    def export_variant_text(
        self,
        original_html: str,
        nodes: Iterable[dict],
        variant: str,
        output_path: Path,
        separator: str = "\n\n",
    ) -> None:
        parts: list[str] = []
        for node in nodes:
            if variant == "adapted":
                text_value = (
                    node.get("human_text")
                    or node.get("adapted_text")
                    or node.get("baseline_text")
                    or node.get("original_text", "")
                )
            else:
                text_value = (
                    node.get(f"{variant}_text")
                    or node.get("baseline_text")
                    or node.get("original_text", "")
                )
            decoded_html = self.placeholder_encoder.decode_fragment(
                text_value, _deserialize_mapping(node.get("placeholders", {}))
            )
            soup = BeautifulSoup(decoded_html, "html.parser")
            plain = soup.get_text(separator=" ", strip=True)
            if plain:
                parts.append(plain)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(separator.join(parts), encoding="utf-8")


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
