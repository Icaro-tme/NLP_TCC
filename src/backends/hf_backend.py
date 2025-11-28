from __future__ import annotations

from typing import Sequence, List, Tuple
import re

from ..core.config import TranslationConfig
from ..translate import TranslationGateway
from .base import TranslatorBackend


class HuggingFaceBackend(TranslatorBackend):
    def __init__(self, config: TranslationConfig) -> None:
        self._config = config
        self._gateway = TranslationGateway(config)

    @staticmethod
    def _extract_glossary_pairs(contexto: str | None) -> List[Tuple[str, str]]:
        if not contexto:
            return []
        pairs: List[Tuple[str, str]] = []
        seen = set()
        lines = [line.strip() for line in contexto.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            m = re.match(r"^(?:Termo|Term|Palavra|Entrada)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
            if m:
                src = m.group(1).strip()
                tgt = ""
                for j in range(idx + 1, min(idx + 4, len(lines))):
                    t = re.match(r"^(?:Tradu[cç][aã]o|Translation|Equivalente|Meaning)\s*[:\-]\s*(.+)$", lines[j], re.IGNORECASE)
                    if t:
                        tgt = t.group(1).strip()
                        break
                if src and tgt and (src, tgt) not in seen:
                    pairs.append((src, tgt))
                    seen.add((src, tgt))
                continue
            sm = re.match(r"^(.+?)\s*(?:=>|->|→|—|-|=)\s*(.+)$", line)
            if sm:
                src = sm.group(1).strip()
                tgt = sm.group(2).strip()
                if src and tgt and (src, tgt) not in seen:
                    pairs.append((src, tgt))
                    seen.add((src, tgt))
        return pairs[:12]

    def translate(self, text: str, source_lang: str, target_lang: str, max_length: int | None = None, contexto: str | None = None) -> str:
        if not text.strip():
            return text
        # Derive forced target terms from contexto (RAG) where applicable.
        forced_terms: List[str] | None = None
        if contexto:
            pairs = self._extract_glossary_pairs(contexto)
            # Keep pairs that actually appear in source text (case-insensitive) to avoid over-constraining.
            filtered: List[str] = []
            lower_src = text.lower()
            for src, tgt in pairs:
                if src and tgt and src.lower() in lower_src:
                    filtered.append(tgt)
                if len(filtered) >= 8:
                    break
            if filtered:
                forced_terms = filtered
        try:
            return self._gateway.translate(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                max_length=max_length,
                forced_terms=forced_terms,
                num_beams=None,
            )
        except Exception:
            # Fallback without constraints if anything goes wrong
            return self._gateway.translate(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                max_length=max_length,
            )

    def batch_translate(
        self,
        texts: Sequence[str],
        source_lang: str,
        target_lang: str,
        max_length: int | None = None,
        contexto: str | None = None,
    ) -> list[str]:
        return [self.translate(t, source_lang, target_lang, max_length=max_length, contexto=contexto) for t in texts]
