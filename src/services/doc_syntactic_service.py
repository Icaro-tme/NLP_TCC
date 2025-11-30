"""Experimental document-level translation with syntactic redistribution heuristics."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List

import spacy

from .doc_level_service import DocLevelTranslationService
from ..telemetry.bus import emit_event
from ..telemetry.events import DocSyntacticSplitEvent


_NLP_MODELS = {
    "en": "en_core_web_sm",
    "es": "es_core_news_sm",
    "pt": "pt_core_news_sm",
}


@dataclass
class DocSyntacticTranslationService(DocLevelTranslationService):
    """Doc-level translation with syntactic redistribution for merged short nodes."""

    nlp_cache: Dict[str, object | None] = field(default_factory=dict)

    def _ensure_nlp(self, lang: str) -> object | None:
        if spacy is None or not lang:
            return None
        if lang in self.nlp_cache:
            return self.nlp_cache[lang]
        model_name = _NLP_MODELS.get(lang)
        if not model_name:
            self.nlp_cache[lang] = None
            return None
        try:
            self.nlp_cache[lang] = spacy.load(model_name)
        except Exception:
            self.nlp_cache[lang] = None
        return self.nlp_cache[lang]

    def _split_group_text(self, text: str, id_count: int, target_lang: str) -> List[str]:
        text = text.strip()
        if id_count <= 1:
            return [text]
        if not text:
            return [""] * id_count

        # 1) Prefer explicit line breaks inserted by the model.
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) == id_count:
            return lines
        if len(lines) > id_count:
            merged_tail = " ".join(lines[id_count - 1 :])
            return lines[: id_count - 1] + [merged_tail.strip()]

        # 2) Try sentence segmentation via spaCy (if available).
        sentences: List[str] = []
        nlp = self._ensure_nlp(target_lang)
        if nlp is not None:
            doc = nlp(text)
            sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        if not sentences:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?;:])\s+", text) if s.strip()]
        if len(sentences) == id_count:
            return sentences
        if len(sentences) > id_count:
            merged_tail = " ".join(sentences[id_count - 1 :])
            return sentences[: id_count - 1] + [merged_tail.strip()]

        # 3) Fallback: proportional split by tokens.
        words = text.split()
        if not words:
            return [""] * id_count
        step = max(1, math.ceil(len(words) / id_count))
        chunks = [" ".join(words[i : i + step]).strip() for i in range(0, len(words), step)]
        if len(chunks) < id_count:
            chunks.extend([""] * (id_count - len(chunks)))
        if len(chunks) > id_count:
            merged_tail = " ".join(chunks[id_count - 1 :])
            chunks = chunks[: id_count - 1] + [merged_tail.strip()]
        return chunks

    def translate_document(self, nodes: List[Dict], target_lang: str) -> Dict[int, str]:
        node_lookup: Dict[int, Dict] = {}
        for original_node in nodes:
            try:
                node_lookup[int(original_node["id"])] = original_node
            except (KeyError, TypeError, ValueError):
                continue

        _linearized, idx, parts = self._translate_linearized(nodes, target_lang)

        out: Dict[int, str] = {}
        for (key, _node_stub), text in zip(idx, parts):
            candidate = text.strip()
            if "," not in key:
                try:
                    nid = int(key)
                except ValueError:
                    continue
                out[nid] = candidate
                self._emit_node_event(node_lookup.get(nid), candidate, target_lang)
                continue

            ids = [int(x) for x in key.split(",") if x.strip()]
            if not ids:
                continue
            segments = self._split_group_text(candidate, len(ids), target_lang)
            if len(segments) != len(ids):
                diff = len(ids) - len(segments)
                if diff > 0:
                    segments.extend([""] * diff)
                else:
                    merged_tail = " ".join(segments[len(ids) - 1 :])
                    segments = segments[: len(ids) - 1] + [merged_tail.strip()]
            emit_event(
                DocSyntacticSplitEvent(
                    node_ids=ids,
                    raw_text=candidate,
                    segments=segments,
                    target_lang=target_lang,
                )
            )
            for nid, chunk in zip(ids, segments):
                clean = chunk.strip()
                out[nid] = clean
                self._emit_node_event(node_lookup.get(nid), clean, target_lang)

        for node in nodes:
            try:
                nid = int(node["id"])
            except (KeyError, TypeError, ValueError):
                continue
            out.setdefault(nid, node.get("original_text", ""))
        return out

