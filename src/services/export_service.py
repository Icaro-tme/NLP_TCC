"""Serviço de exportação de variantes de tradução para HTML.

Responsabilidade:
Reconstrói um HTML a partir dos nós persistidos, inserindo o texto traduzido
correspondente à variante solicitada ("baseline" ou "adapted").

Regra especial solicitada:
Ao exportar a variante "adapted" caso exista `human_text` preenchido para o nó,
esse texto humano tem prioridade sobre o texto adaptado gerado pelo modelo.
Isso permite que correções manuais sejam refletidas diretamente na variante
adaptada sem alterar a baseline.

Observação:
Placeholders internos são decodificados para restaurar marcas/trechos inline
que foram protegidos durante o processo de tradução.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from ..core.placeholders import PlaceholderEncoder


class HTMLExportService:
    """Reconstrói variantes HTML a partir dos nós persistidos.

    Para a variante "adapted" prioriza `human_text` quando disponível.
    """

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
            # Adiciona atributo estável com o ID do banco 
            # Ex.: <div data-node-id="0.2.0" data-node-database-id="17"> ...
            db_id = node.get("id") or node.get("node_id")  
            if db_id is not None:
                element.attrs["data-node-database-id"] = str(db_id)
            # Prioridade: se variante == adapted e há human_text, usar humano.
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
            element.clear()
            decoded_html = self.placeholder_encoder.decode_fragment(
                text_value, _deserialize_mapping(node.get("placeholders", {}))
            )
            # Parse the decoded HTML so inline tags are not escaped as text
            fragment = BeautifulSoup(decoded_html, "html.parser")
            # Envolve conteúdo em um wrapper clicável garantindo área de clique
            wrapper = soup.new_tag("span")
            wrapper.attrs["class"] = (element.get("class", []) or []) + ["tcc-node-wrapper"]
            if db_id is not None:
                wrapper.attrs["data-node-database-id"] = str(db_id)
            # move conteúdo decodificado para dentro do wrapper
            content_iter = list(fragment.body.contents if fragment.body else fragment.contents)
            for child in content_iter:
                wrapper.append(child)
            element.append(wrapper)
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
