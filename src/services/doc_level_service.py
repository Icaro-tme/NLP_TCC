"""Document-level translation: linearize all nodes with <N#> markers and translate once."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from bs4 import BeautifulSoup

from ..backends.base import TranslatorBackend
from ..backends.hf_backend import HuggingFaceBackend
from ..backends.google_backend import GoogleLLMBackend
from ..core.config import PipelineConfig, RagConfig
from ..rag.retriever import Retriever


MARKER_OPEN = "<N{idx}>"
MARKER_CLOSE = "</N{idx}>"


@dataclass
class DocLevelTranslationService:
    config: PipelineConfig
    backend: TranslatorBackend | None = None

    def _ensure_backend(self) -> TranslatorBackend:
        if self.backend:
            return self.backend
        if self.config.translation.backend == "google":
            self.backend = GoogleLLMBackend()
        else:
            self.backend = HuggingFaceBackend(self.config.translation)
        return self.backend

    def _maybe_merge_short_nodes(self, nodes: List[Dict]) -> List[Dict]:
        threshold = self.config.translation.short_node_merge_chars
        if threshold <= 0:
            return nodes
        merged: List[Dict] = []
        buffer: List[Dict] = []
        acc_len = 0
        def flush():
            nonlocal buffer, acc_len
            if not buffer:
                return
            if len(buffer) == 1:
                merged.append(buffer[0])
            else:
                # create synthetic group node preserving all ids in order
                group_text = "\n".join(n.get("original_text", "") for n in buffer)
                group_ids = ",".join(str(n["id"]) for n in buffer)
                merged.append({"id": group_ids, "original_text": group_text})
            buffer = []
            acc_len = 0
        for n in nodes:
            t = n.get("original_text", "")
            if len(t.strip()) <= threshold:
                buffer.append(n)
                acc_len += len(t)
            else:
                flush()
                merged.append(n)
        flush()
        return merged

    def linearize(self, nodes: Iterable[Dict]) -> Tuple[str, List[Tuple[str, Dict]]]:
        node_list = list(nodes)
        node_list = self._maybe_merge_short_nodes(node_list)
        lines: List[str] = []
        index: List[Tuple[str, Dict]] = []  # (key, node)
        for i, node in enumerate(node_list):
            key = str(node["id"]) if isinstance(node["id"], int) else str(node["id"])  # may be csv of ids
            content = node.get("original_text", "")
            lines.append(MARKER_OPEN.format(idx=i) + content + MARKER_CLOSE.format(idx=i))
            index.append((key, node))
        return "\n".join(lines), index

    def parse_translated(self, translated: str) -> List[str]:
        pattern = re.compile(r"<N(\d+)>\s*(.*?)\s*</N\1>", re.DOTALL)
        parts = [m.group(2) for m in pattern.finditer(translated)]
        return parts

    def translate_document(self, nodes: List[Dict], target_lang: str) -> Dict[int, str]:
        backend = self._ensure_backend()
        linearized, idx = self.linearize(nodes)

        # RAG: recuperar contexto se habilitado
        contexto: str | None = None
        rag_cfg: RagConfig | None = getattr(self.config, "rag", None)
        if rag_cfg and rag_cfg.enabled and rag_cfg.top_k > 0 and self.config.paths is not None:
            index_dir = rag_cfg.index_dir or (self.config.paths.data_dir / "rag_index")
            retriever = Retriever(model_name=rag_cfg.model, index_dir=index_dir)
            # Construir índice se necessário a partir de diretórios padrão
            if not retriever.has_index():
                source_dirs = [self.config.paths.glossario_dir, self.config.paths.corpus_dir]
                retriever.build_index(source_dirs)
            # Query: usar começo do documento linearizado (corta para 4000 chars para embedding)
            query_text = linearized[:4000]
            snippets = retriever.retrieve(query_text, top_k=rag_cfg.top_k)
            contexto = Retriever.build_context(snippets, max_chars=rag_cfg.max_context_chars)

        translated = backend.translate(
            linearized,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
            contexto=contexto,
        )
        parts = self.parse_translated(translated)
        out: Dict[int, str] = {}
        for (key, node), text in zip(idx, parts):
            if "," in key:  # group, split by lines as heuristic
                ids = [int(x) for x in key.split(",")]
                chunks = text.splitlines()
                if len(chunks) == len(ids):
                    for i, nid in enumerate(ids):
                        out[nid] = chunks[i].strip()
                else:
                    # assign whole to first, empty to rest as fallback
                    out[ids[0]] = text.strip()
                    for nid in ids[1:]:
                        out[nid] = ""
            else:
                out[int(key)] = text.strip()
        return out
