"""Abstract translator backend interface to allow multiple translation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence


class TranslatorBackend(ABC):
    """Defines the minimal contract any translation provider must satisfy.

    Methods operate on raw text strings; higher-level orchestration (segmentation,
    placeholder handling) happens outside in services.
    """

    @abstractmethod
    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        max_length: int | None = None,
        contexto: str | None = None,
    ) -> str:
        """Traduz um fragmento de texto. Parâmetro "contexto" permite injetar
        informações auxiliares (RAG, glossário), que alguns backends podem utilizar
        para orientar a tradução. Backends que não suportam contexto simplesmente ignoram."""
        raise NotImplementedError

    def batch_translate(
        self,
        texts: Sequence[str],
        source_lang: str,
        target_lang: str,
        max_length: int | None = None,
        contexto: str | None = None,
    ) -> list[str]:
        """Implementação padrão: traduz cada item em sequência."""
        return [
            self.translate(t, source_lang=source_lang, target_lang=target_lang, max_length=max_length, contexto=contexto)
            for t in texts
        ]
