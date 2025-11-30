"""Orquestração enxuta para traduções diretas por nó (Google-only).

Este serviço foi simplificado para utilizar exclusivamente o backend Google Gemini.
Ele mantém suporte aos modos "node" e "window" para efeitos de compatibilidade
e observabilidade, mas recomenda-se priorizar o modo "doc" no serviço de nível
de documento para melhor qualidade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from ..core.config import PipelineConfig
from ..backends.base import TranslatorBackend
from ..backends.google_backend import GoogleLLMBackend
from ..segmentation import build_windows, split_window_translation
from ..telemetry.bus import emit_event
from ..telemetry.events import NodeTranslationEvent, WindowTranslationEvent


@dataclass
class TranslationService:
    """Coordena a tradução bruta em modos nó e janela usando Google Gemini."""

    config: PipelineConfig
    backend: TranslatorBackend | None = None
    mode: str = "node"  # "node" | "window"

    def _emit_node_event(self, node: Dict | None, translated_text: str, target_lang: str) -> None:
        if not node:
            return
        try:
            node_id = int(node["id"])
        except (KeyError, TypeError, ValueError):
            return
        emit_event(
            NodeTranslationEvent(
                node_id=node_id,
                node_path=node.get("node_path"),
                original_text=node.get("original_text", ""),
                translated_text=translated_text,
                target_lang=target_lang,
                mode=self.mode,
            )
        )

    def _ensure_backend(self) -> TranslatorBackend:
        if self.backend:
            return self.backend
        self.backend = GoogleLLMBackend()
        return self.backend

    def translate_node(self, node: Dict, target_lang: str) -> str:
        backend = self._ensure_backend()
        original_text = node.get("original_text", "")
        if not original_text.strip():
            return original_text
        translated = backend.translate(
            text=original_text,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
        )
        self._emit_node_event(node, translated, target_lang)
        return translated

    def translate_nodes_windowed(self, nodes: Iterable[Dict], target_lang: str) -> Dict[int, str]:
        """Translate nodes grouped into context windows, returning mapping id->translated_text."""
        backend = self._ensure_backend()
        windows = build_windows(nodes)
        out: Dict[int, str] = {}
        for node_group, window_text in windows:
            translated_window = backend.translate(
                text=window_text,
                source_lang=self.config.source_lang,
                target_lang=target_lang,
            )
            window_node_ids: List[int] = []
            for candidate in node_group:
                try:
                    window_node_ids.append(int(candidate["id"]))
                except (KeyError, TypeError, ValueError):
                    continue
            emit_event(
                WindowTranslationEvent(
                    node_ids=window_node_ids,
                    window_source=window_text,
                    window_translation=translated_window,
                    target_lang=target_lang,
                )
            )
            splits = split_window_translation(translated_window)
            lookup = {str(n["id"]): n for n in node_group}
            for node_id_str, translated in splits:
                if node_id_str in lookup:
                    node_obj = lookup[node_id_str]
                    out[node_obj["id"]] = translated
                    self._emit_node_event(node_obj, translated, target_lang)
        return out

