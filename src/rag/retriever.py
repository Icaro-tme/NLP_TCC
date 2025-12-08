"""Módulo RAG alimentado por SQLite para recuperar contexto jurídico/glossário."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from ..persistence.db import Database
from ..persistence.rag_repos import CorpusRepository, GlossaryRepository


@dataclass
class RagDocument:
    doc_id: str
    text: str
    metadata: Dict[str, object]


@dataclass
class RagIndex:
    model_name: str
    documents: List[RagDocument]
    embeddings: np.ndarray 


class Retriever:
    def __init__(self, model_name: str, index_dir: Path, db_path: Path) -> None:
        self.model_name = model_name
        self.index_dir = index_dir
        self.index_path = index_dir / "rag_index.pkl"
        self.db_path = db_path
        self._model: SentenceTransformer | None = None
        self._index: RagIndex | None = None
        index_dir.mkdir(parents=True, exist_ok=True)

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def has_index(self) -> bool:
        return self.index_path.exists()

    def build_index(self) -> None:
        db = Database(self.db_path)
        db.init_schema()
        gloss_repo = GlossaryRepository(db)
        corpus_repo = CorpusRepository(db)

        documents: List[RagDocument] = []

        try:
            for entry in gloss_repo.list_entries():
                text_lines = [
                    f"Termo ({entry['lang_src']}): {entry['term_src']}",
                    f"Tradução ({entry['lang_tgt']}): {entry['term_tgt']}",
                ]
                if entry.get("notes"):
                    text_lines.append(f"Notas: {entry['notes']}")
                text = "\n".join(text_lines)
                documents.append(
                    RagDocument(
                        doc_id=f"glossary:{entry['id']}",
                        text=text,
                        metadata={
                            "type": "glossary",
                            "lang_src": entry["lang_src"],
                            "lang_tgt": entry["lang_tgt"],
                            "term_src": entry["term_src"],
                            "term_tgt": entry["term_tgt"],
                            "notes": entry.get("notes"),
                        },
                    )
                )

            for snippet in corpus_repo.list_snippets():
                text = snippet["text"].strip()
                if snippet.get("notes"):
                    text = f"{text}\nNotas: {snippet['notes']}"
                documents.append(
                    RagDocument(
                        doc_id=f"corpus:{snippet['id']}",
                        text=text,
                        metadata={
                            "type": "corpus",
                            "language": snippet["language"],
                            "tags": snippet.get("tags", []),
                        },
                    )
                )

            if not documents:
                raise RuntimeError("Nenhum texto localizado para construir índice RAG.")

            model = self._load_model()
            corpus_texts = [doc.text.replace("\n", " ")[:5000] for doc in documents]
            embeddings = model.encode(
                corpus_texts,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            rag_index = RagIndex(model_name=self.model_name, documents=documents, embeddings=embeddings)
            with self.index_path.open("wb") as f:
                pickle.dump(rag_index, f)
            self._index = rag_index
        finally:
            db.close()

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

    def retrieve(
        self,
        query_text: str,
        top_k: int = 3,
        *,
        source_lang: str | None = None,
        target_lang: str | None = None,
    ) -> List[Tuple[str, str, float, Dict[str, object]]]:
        if top_k <= 0:
            return []
        index = self._ensure_index()
        model = self._load_model()
        query_emb = model.encode([query_text], convert_to_numpy=True, normalize_embeddings=True)[0]
        scores = (index.embeddings @ query_emb).tolist()
        ranked: List[Tuple[int, float]] = []
        for idx, score in enumerate(scores):
            doc = index.documents[idx]
            if not self._is_relevant(doc.metadata, source_lang, target_lang):
                continue
            ranked.append((idx, score))
        ranked = sorted(ranked, key=lambda x: x[1], reverse=True)[:top_k]
        results: List[Tuple[str, str, float, Dict[str, object]]] = []
        for idx, score in ranked:
            doc = index.documents[idx]
            results.append((doc.doc_id, doc.text, score, doc.metadata))
        return results

    @staticmethod
    def build_context(
        snippets: List[Tuple[str, str, float, Dict[str, object]]],
        max_chars: int,
    ) -> str:
        parts: List[str] = []
        total = 0
        for doc_id, text, score, metadata in snippets:
            header_bits = [f"Fonte: {doc_id}", f"score={score:.3f}"]
            if metadata.get("type") == "glossary":
                header_bits.append(
                    f"langs={metadata.get('lang_src')}->{metadata.get('lang_tgt')}"
                )
            if metadata.get("type") == "corpus":
                header_bits.append(f"lang={metadata.get('language')}")
                tags = metadata.get("tags")
                if (
                    isinstance(tags, Iterable)
                    and not isinstance(tags, (str, bytes))
                    and tags
                ):
                    header_bits.append("tags=" + ",".join(str(t) for t in tags))
            header = "[" + " | ".join(header_bits) + "]"
            fragment = f"{header}\n{text}\n"
            if total + len(fragment) > max_chars:
                break
            parts.append(fragment)
            total += len(fragment)
        return "\n".join(parts)

    @staticmethod
    def _is_relevant(
        metadata: Dict[str, object],
        source_lang: Optional[str],
        target_lang: Optional[str],
    ) -> bool:
        doc_type = metadata.get("type")
        if doc_type == "glossary":
            if target_lang and metadata.get("lang_tgt") != target_lang:
                return False
            if source_lang and metadata.get("lang_src") not in {source_lang, "multi"}:
                return False
            return True
        if doc_type == "corpus":
            language = metadata.get("language")
            # Corpus deve estar no idioma ALVO (para onde estamos traduzindo)
            # Glossário usa source→target, mas corpus é texto de exemplo no idioma final
            if target_lang:
                return language == target_lang
            if source_lang:
                return language == source_lang
            return True
        return True
