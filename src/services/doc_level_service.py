"""Document-level translation: linearize all nodes with <N#> markers and translate once."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

from ..backends.base import TranslatorBackend
from ..backends.hf_backend import HuggingFaceBackend
from ..backends.google_backend import GoogleLLMBackend
from ..core.config import PipelineConfig, RagConfig
from ..rag.retriever import Retriever
from ..telemetry.bus import emit_event
from ..telemetry.events import (
    DocLinearizationEvent,
    DocTranslationEvent,
    NodeTranslationEvent,
    RagContextEvent,
)


MARKER_OPEN = "<N{idx}>"
MARKER_CLOSE = "</N{idx}>"


@dataclass
class DocLevelTranslationService:
    config: PipelineConfig
    backend: TranslatorBackend | None = None
    last_context: str | None = None

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
                mode=self.config.translation.strategy,
            )
        )

    def _build_context(self, linearized: str, target_lang: str | None = None) -> str | None:
        """Gera contexto RAG opcional para doc-level e variações."""
        rag_cfg: RagConfig | None = getattr(self.config, "rag", None)
        if not (rag_cfg and rag_cfg.enabled and rag_cfg.top_k > 0 and self.config.paths is not None):
            return None
        index_dir = rag_cfg.index_dir or (self.config.paths.data_dir / "rag_index")
        retriever = Retriever(
            model_name=rag_cfg.model,
            index_dir=index_dir,
            db_path=self.config.paths.db_path,
        )
        if not retriever.has_index():
            retriever.build_index()
        query_text = linearized[:4000]
        snippets = retriever.retrieve(
            query_text,
            top_k=rag_cfg.top_k,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
        )
        contexto = Retriever.build_context(snippets, max_chars=rag_cfg.max_context_chars)
        if contexto:
            emit_event(RagContextEvent(context_text=contexto, target_lang=target_lang))
        return contexto

    @staticmethod
    def _extract_glossary_pairs(contexto: str | None) -> List[Tuple[str, str]]:
        if not contexto:
            return []
        pairs: List[Tuple[str, str]] = []
        seen: Set[Tuple[str, str]] = set()
        lines = [line.strip() for line in contexto.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            term_match = re.match(r"^(?:Termo|Term|Palavra|Entrada)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
            if term_match:
                src = term_match.group(1).strip()
                tgt = ""
                for look_ahead in range(idx + 1, min(idx + 4, len(lines))):
                    trans_match = re.match(r"^(?:Tradu[cç][aã]o|Translation|Equivalente|Meaning)\s*[:\-]\s*(.+)$", lines[look_ahead], re.IGNORECASE)
                    if trans_match:
                        tgt = trans_match.group(1).strip()
                        break
                if src and tgt and (src, tgt) not in seen:
                    pairs.append((src, tgt))
                    seen.add((src, tgt))
                continue
            simple_match = re.match(r"^(.+?)\s*(?:=>|->|→|—|-|=)\s*(.+)$", line)
            if simple_match:
                src = simple_match.group(1).strip()
                tgt = simple_match.group(2).strip()
                if src and tgt and (src, tgt) not in seen:
                    pairs.append((src, tgt))
                    seen.add((src, tgt))
        return pairs[:20]

    @staticmethod
    def _apply_glossary_bias(text: str, pairs: List[Tuple[str, str]]) -> Tuple[str, Dict[str, str]]:
        placeholder_map: Dict[str, str] = {}
        biased_text = text
        for idx, (src, tgt) in enumerate(pairs):
            src_clean = src.strip()
            tgt_clean = tgt.strip()
            if not src_clean or not tgt_clean:
                continue
            token = f"<<RAG{idx}>>"
            pattern = re.compile(rf"(?<!\w){re.escape(src_clean)}(?!\w)", re.IGNORECASE)
            if not pattern.search(biased_text):
                continue
            biased_text = pattern.sub(token, biased_text)
            placeholder_map[token] = tgt_clean
        return biased_text, placeholder_map

    @staticmethod
    def _restore_glossary_terms(text: str, placeholder_map: Dict[str, str]) -> str:
        restored = text
        for token, tgt in placeholder_map.items():
            restored = restored.replace(token, tgt)
        return restored

    def _translate_linearized(
        self, nodes: List[Dict], target_lang: str
    ) -> Tuple[str, List[Tuple[str, Dict]], List[str]]:
        backend = self._ensure_backend()
        linearized, idx = self.linearize(nodes)
        mapping_payload: List[Dict[str, object]] = []
        for marker_idx, (key, node) in enumerate(idx):
            mapping_payload.append(
                {
                    "marker": marker_idx,
                    "node_id": key,
                    "original": node.get("original_text", ""),
                }
            )
        emit_event(
            DocLinearizationEvent(
                linearized_text=linearized,
                mapping=mapping_payload,
                target_lang=target_lang,
            )
        )
        contexto = self._build_context(linearized, target_lang=target_lang)
        self.last_context = contexto
        glossary_pairs = self._extract_glossary_pairs(contexto)
        payload_text = linearized
        placeholder_map: Dict[str, str] = {}
        if glossary_pairs and isinstance(backend, HuggingFaceBackend):
            payload_text, placeholder_map = self._apply_glossary_bias(linearized, glossary_pairs)
        translated = backend.translate(
            payload_text,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
            contexto=contexto,
        )
        if placeholder_map:
            translated = self._restore_glossary_terms(translated, placeholder_map)
        emit_event(
            DocTranslationEvent(
                linearized_text=linearized,
                translated_text=translated,
                target_lang=target_lang,
            )
        )
        parts = self.parse_translated(translated)
        return linearized, idx, parts

    def translate_document(self, nodes: List[Dict], target_lang: str) -> Dict[int, str]:
        node_lookup: Dict[int, Dict] = {}
        for original_node in nodes:
            try:
                node_lookup[int(original_node["id"])] = original_node
            except (KeyError, TypeError, ValueError):
                continue

        _linearized, idx, parts = self._translate_linearized(nodes, target_lang)
        out: Dict[int, str] = {}
        for (key, node), text in zip(idx, parts):
            if "," in key:  # group, split by lines as heuristic
                ids = [int(x) for x in key.split(",")]
                chunks = text.splitlines()
                if len(chunks) == len(ids):
                    for i, nid in enumerate(ids):
                        chunk = chunks[i].strip()
                        out[nid] = chunk
                        self._emit_node_event(node_lookup.get(nid), chunk, target_lang)
                else:
                    # assign whole to first, empty to rest as fallback
                    primary = text.strip()
                    out[ids[0]] = primary
                    self._emit_node_event(node_lookup.get(ids[0]), primary, target_lang)
                    for nid in ids[1:]:
                        out[nid] = ""
                        self._emit_node_event(node_lookup.get(nid), "", target_lang)
            else:
                clean = text.strip()
                nid = int(key)
                out[nid] = clean
                self._emit_node_event(node_lookup.get(nid), clean, target_lang)
        return out
