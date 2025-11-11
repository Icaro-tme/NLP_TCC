"""Orquestração enxuta para traduções diretas por nó."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from ..core.config import PipelineConfig
from ..translate import TranslationGateway
from ..backends.base import TranslatorBackend
from ..backends.hf_backend import HuggingFaceBackend
from ..segmentation import build_windows, split_window_translation


@dataclass
class TranslationService:
    """Coordena somente a etapa de tradução bruta com o modelo Hugging Face."""

    config: PipelineConfig
    gateway: TranslationGateway | None = None
    backend: TranslatorBackend | None = None
    mode: str = "node"  # "node" | "window"

    def _ensure_backend(self) -> TranslatorBackend:
        if self.backend:
            return self.backend
        # Default to HF backend wrapping existing gateway.
        if self.gateway is None:
            self.gateway = TranslationGateway(self.config.translation)
        self.backend = HuggingFaceBackend(self.config.translation)
        return self.backend

    def translate_node(self, node: Dict, target_lang: str) -> str:
        backend = self._ensure_backend()
        original_text = node.get("original_text", "")
        if not original_text.strip():
            return original_text
        return backend.translate(
            text=original_text,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
        )

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
            splits = split_window_translation(translated_window)
            lookup = {str(n["id"]): n for n in node_group}
            for node_id_str, translated in splits:
                if node_id_str in lookup:
                    out[lookup[node_id_str]["id"]] = translated
        return out

