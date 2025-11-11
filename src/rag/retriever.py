"""Módulo RAG simples para recuperar contexto jurídico/glossário.

Fluxo:
1. Carrega/gera embeddings para arquivos em diretórios configurados (glossário, corpus).
2. Persiste índice (pickle) para evitar recomputação.
3. Fornece método retrieve(query_text, top_k) retornando trechos mais similares.

Observações:
- Usa SentenceTransformer para embeddings (multilingue).
- Similaridade: cosine via numpy.
- Limita tamanho total concatenado por max_context_chars.
"""

from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup


@dataclass
class RagIndex:
    model_name: str
    documents: List[Tuple[str, str]]  # (doc_id, text)
    embeddings: np.ndarray  # shape (N, D)


class Retriever:
    def __init__(self, model_name: str, index_dir: Path) -> None:
        self.model_name = model_name
        self.index_dir = index_dir
        self.index_path = index_dir / "rag_index.pkl"
        self._model: SentenceTransformer | None = None
        self._index: RagIndex | None = None
        index_dir.mkdir(parents=True, exist_ok=True)

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def has_index(self) -> bool:
        return self.index_path.exists()

    def build_index(self, source_dirs: List[Path]) -> None:
        texts: List[Tuple[str, str]] = []
        for d in source_dirs:
            if not d.exists():
                continue
            for p in d.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".txt", ".md", ".html"}:
                    try:
                        raw = p.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue
                    # Remover marcações HTML quando aplicável
                    if p.suffix.lower() == ".html":
                        try:
                            cleaned = BeautifulSoup(raw, "lxml").get_text(" ")
                        except Exception:
                            cleaned = raw
                    else:
                        cleaned = raw
                    cleaned = cleaned.replace("\n", " ").strip()
                    if cleaned:
                        texts.append((str(p), cleaned[:5000]))  # corta documento longo
        if not texts:
            raise RuntimeError("Nenhum texto localizado para construir índice RAG.")
        model = self._load_model()
        corpus_texts = [t for _, t in texts]
        embeddings = model.encode(corpus_texts, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
        rag_index = RagIndex(model_name=self.model_name, documents=texts, embeddings=embeddings)
        with self.index_path.open("wb") as f:
            pickle.dump(rag_index, f)
        self._index = rag_index

    def load_index(self) -> None:
        if not self.has_index():
            raise FileNotFoundError("Índice RAG inexistente. Execute build_index primeiro.")
        with self.index_path.open("rb") as f:
            self._index = pickle.load(f)
        if self._index.model_name != self.model_name:
            # Modelo diferente: precisamos reconstruir para consistência.
            raise RuntimeError("Modelo de embeddings divergente. Reconstruir índice.")

    def _ensure_index(self) -> RagIndex:
        if self._index is None:
            self.load_index()
        assert self._index is not None
        return self._index

    def retrieve(self, query_text: str, top_k: int = 3) -> List[Tuple[str, str, float]]:
        if top_k <= 0:
            return []
        index = self._ensure_index()
        model = self._load_model()
        query_emb = model.encode([query_text], convert_to_numpy=True, normalize_embeddings=True)[0]
        scores = (index.embeddings @ query_emb).tolist()  # cosine (embeddings normalizadas)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        results: List[Tuple[str, str, float]] = []
        for idx, score in ranked:
            doc_id, text = index.documents[idx]
            results.append((doc_id, text, score))
        return results

    @staticmethod
    def build_context(snippets: List[Tuple[str, str, float]], max_chars: int) -> str:
        parts: List[str] = []
        total = 0
        for doc_id, text, score in snippets:
            fragment = f"[Fonte: {Path(doc_id).name} | score={score:.3f}]\n{text}\n"
            if total + len(fragment) > max_chars:
                break
            parts.append(fragment)
            total += len(fragment)
        return "\n".join(parts)
