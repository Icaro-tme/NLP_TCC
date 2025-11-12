from __future__ import annotations

from typing import Sequence

from ..core.config import TranslationConfig
from ..translate import TranslationGateway
from .base import TranslatorBackend


class HuggingFaceBackend(TranslatorBackend):
    def __init__(self, config: TranslationConfig) -> None:
        self._config = config
        self._gateway = TranslationGateway(config)

    def translate(self, text: str, source_lang: str, target_lang: str, max_length: int | None = None, contexto: str | None = None) -> str:
        if not text.strip():
            return text
        return self._gateway.translate(text=text, source_lang=source_lang, target_lang=target_lang, max_length=max_length)

    def batch_translate(
        self,
        texts: Sequence[str],
        source_lang: str,
        target_lang: str,
        max_length: int | None = None,
        contexto: str | None = None,
    ) -> list[str]:
        return [self.translate(t, source_lang, target_lang, max_length=max_length, contexto=contexto) for t in texts]
