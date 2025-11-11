"""Stub Google LLM backend for later integration (Gemini / AI Studio)."""

from __future__ import annotations

import os
from typing import Sequence

try:
    import google.generativeai as genai  # type: ignore
except ImportError:  # pragma: no cover
    genai = None

from .base import TranslatorBackend


DEFAULT_MODEL = "gemini-1.5-flash"  # default; will fallback if unavailable


class GoogleLLMBackend(TranslatorBackend):
    """Minimal placeholder; raises if no API key provided.

    Expected env var: GOOGLE_API_KEY
    Implementation outline (not active yet):
      - from google import genai
      - client = genai.Client(api_key=...)
      - prompt engineering to preserve <ph data-id="PHxxxx"> markers.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self.api_key = os.getenv("GOOGLE_API_KEY")

    def translate(self, text: str, source_lang: str, target_lang: str, max_length: int | None = None, contexto: str | None = None) -> str:
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY ausente. Defina variável de ambiente antes de usar --backend google.")
        if genai is None:
            raise RuntimeError("Biblioteca google-generativeai não instalada. Execute: pip install google-generativeai")
        genai.configure(api_key=self.api_key)
        # Construir prompt com possível contexto recuperado (RAG)
        prompt = self._build_prompt(text, source_lang, target_lang, contexto=contexto)
        candidates = [self.model, "gemini-1.5-pro", "gemini-1.0-pro"]
        # Try direct names first; if all fail, list models dynamically and pick one supporting generateContent
        last_err: Exception | None = None
        for name in candidates:
            model = genai.GenerativeModel(name)
            try:
                response = model.generate_content(prompt)
                break
            except Exception as e:
                last_err = e
                response = None
        if response is None:
            try:
                available = list(genai.list_models())
                # Filter models that support generateContent
                prefers = [m for m in available if hasattr(m, "supported_generation_methods") and "generateContent" in getattr(m, "supported_generation_methods", [])]
                # Prefer 1.5 flash/pro if present
                ordered = sorted(prefers, key=lambda m: ("1.5" not in m.name, "flash" not in m.name, "pro" not in m.name))
                chosen = ordered[0] if ordered else None
                if not chosen:
                    raise RuntimeError("Nenhum modelo com generateContent disponível na conta.")
                model = genai.GenerativeModel(chosen.name)
                response = model.generate_content(prompt)
            except Exception as e:
                raise RuntimeError(
                    f"Falha em todos os modelos Google ({', '.join(candidates)}), e seleção automática falhou: {e}"
                ) from (last_err or e)
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        # Fallback: concatenar partes
        parts = []
        for c in getattr(response, "candidates", []):
            for ct in getattr(c, "content", []).parts:
                if hasattr(ct, "text"):
                    parts.append(ct.text)
        return "\n".join(parts).strip() or text

    def batch_translate(
        self,
        texts: Sequence[str],
        source_lang: str,
        target_lang: str,
        max_length: int | None = None,
        contexto: str | None = None,
    ) -> list[str]:
        return [self.translate(t, source_lang, target_lang, max_length=max_length, contexto=contexto) for t in texts]

    def _build_prompt(self, linearized: str, source_lang: str, target_lang: str, contexto: str | None = None) -> str:
        lang_name = {"en": "English", "pt": "Portuguese"}.get(target_lang, target_lang)
        base = (
            "You are a legal-domain translation engine. Translate from Portuguese to "
            f"{lang_name} while strictly preserving segment markers <N#> and inline placeholders <ph data-id=\"...\">.\n"
            "Rules:\n"
            "1. Do NOT remove, reorder, merge, or create segment markers.\n"
            "2. Preserve <ph data-id=\"PHxxxx\"> tags unchanged except translating their textual inner content.\n"
            "3. Output ONLY the translated segments; no explanations.\n"
            "4. Keep whitespace minimal inside markers.\n"
        )
        ctx_block = ""
        if contexto:
            ctx_block = f"\nAdditional legal context (retrieved):\n{contexto}\n"
        return base + ctx_block + "\nSource segments:\n" + linearized + "\n\nTranslate now:" 
