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
    def translate(self, text: str, source_lang: str, target_lang: str, max_length: int | None = None) -> str:
        """Translate a single text fragment."""
        raise NotImplementedError

    def batch_translate(
        self,
        texts: Sequence[str],
        source_lang: str,
        target_lang: str,
        max_length: int | None = None,
    ) -> list[str]:
        """Default naive batch implementation; override if backend can optimize."""
        return [
            self.translate(t, source_lang=source_lang, target_lang=target_lang, max_length=max_length)
            for t in texts
        ]
