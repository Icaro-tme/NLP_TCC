"""Pipeline unificado de tradução (node, window, doc) usando Google.

Responsabilidades:
- Modo doc: uma chamada única, lineariza com `<N#>...</N#>`, emite `DocLinearizationEvent` e
    um único `DocTranslationEvent`, depois emite `NodeMappingEvent` por nó ao persistir/mapping.
- Modo node: uma chamada por nó, emite `NodeTranslationEvent` por nó.
- Modo window: agrupa por `window_size`, emite `WindowTranslationEvent` por janela e
    `NodeMappingEvent` por nó (mapeamento de janela).

Observações:
- Sem fusão de nós. Cada nó possui seu próprio marcador `<N{id}>` no doc-level.
- Eventos de RAG (`CorpusRetrievalEvent`, `RagContextEvent`) são emitidos separadamente antes da tradução.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple
from collections import Counter
import json

from ..core.config import PipelineConfig, RagConfig
from ..backends.google_backend import GoogleLLMBackend
from ..telemetry.bus import emit_event
from ..telemetry.events import (
    DocLinearizationEvent,
    DocTranslationEvent,
    NodeTranslationEvent,
    NodeMappingEvent,
    WindowTranslationEvent,
    DocPromptEvent,
    RagContextEvent,
    CorpusRetrievalEvent,
    GlossaryMatchesEvent,
    PlaceholderErrorEvent,
)
from ..rag.retriever import Retriever
from ..persistence.db import Database
from ..persistence.rag_repos import GlossaryRepository


MARKER_OPEN = "<N{idx}>"
MARKER_CLOSE = "</N{idx}>"
PH_OPEN_RE = re.compile(r"<ph\s+data-id=\"(PH\d+)\"\s*/?>", re.IGNORECASE)
PH_TAG_ITER_RE = re.compile(r"<ph\s+data-id=\"(PH\d+)\"\s*(/?)>|</ph>", re.IGNORECASE)


class PlaceholderValidationError(RuntimeError):
    """Erro lançado quando a tradução corrompe placeholders <ph data-id="PHxxxx">."""


def _extract_placeholder_tokens(text: str) -> List[str]:
    if not text:
        return []
    return [token.upper() for token in PH_OPEN_RE.findall(text)]


@dataclass
class ServicoTraducao:
    config: PipelineConfig
    backend: GoogleLLMBackend | None = None
    window_size: int = 3
    doc_name: str | None = None
    document_id: int | None = None
    placeholder_errors: List[Dict[str, Any]] = field(default_factory=list, init=False)
    glossary_match_records: List[Dict[str, Any]] = field(default_factory=list, init=False)
    glossary_cache: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict, init=False)
    glossary_enabled: bool = True

    # ---------------- Backend -----------------
    def _ensure_backend(self) -> GoogleLLMBackend:
        if self.backend:
            return self.backend
        self.backend = GoogleLLMBackend()
        return self.backend

    # ---------------- Glossary helpers -----------------
    def _glossary_cache_key(self, target_lang: str) -> str:
        return f"{self.config.source_lang}->{target_lang}"

    def _get_glossary_entries(self, target_lang: str) -> List[Dict[str, Any]]:
        key = self._glossary_cache_key(target_lang)
        if key in self.glossary_cache:
            return self.glossary_cache[key]
        entries: List[Dict[str, Any]] = []
        paths = getattr(self.config, "paths", None)
        if paths and paths.db_path:
            db = Database(paths.db_path)
            try:
                repo = GlossaryRepository(db)
                entries = repo.list_entries(lang_src=self.config.source_lang, lang_tgt=target_lang)
            finally:
                db.close()
        # Normalize entries to ensure consistent structure
        normalized: List[Dict[str, Any]] = []
        for entry in entries:
            term_src = (entry.get("term_src") or "").strip()
            term_tgt = (entry.get("term_tgt") or "").strip()
            if not term_src or not term_tgt:
                continue
            normalized.append(
                {
                    "id": entry.get("id"),
                    "term_src": term_src,
                    "term_tgt": term_tgt,
                    "notes": entry.get("notes") or "",
                }
            )
        self.glossary_cache[key] = normalized
        return normalized

    def _compile_glossary_pattern(self, term_src: str) -> re.Pattern:
        pattern_text = re.escape(term_src)
        # Use word boundaries only when term is alphanumeric without spaces
        if re.search(r"[A-Za-z0-9Á-Ýá-ý]", term_src) and not re.search(r"\s", term_src):
            pattern_text = r"(?<!\w)" + pattern_text + r"(?!\w)"
        return re.compile(pattern_text, re.IGNORECASE | re.MULTILINE)

    def _prepare_glossary_for_text(
        self,
        node: Dict,
        text: str,
        target_lang: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not self.glossary_enabled:
            return text, []
        entries = self._get_glossary_entries(target_lang)
        if not entries or not text:
            return text, []
        node_id_raw = node.get("id")
        try:
            node_id = int(node_id_raw) if node_id_raw is not None else None
        except (TypeError, ValueError):
            node_id = None
        matches: List[Dict[str, Any]] = []
        processed_text = text
        for entry in entries:
            pattern = self._compile_glossary_pattern(entry["term_src"])
            for match in pattern.finditer(processed_text):
                matches.append(
                    {
                        "entry_id": entry["id"],
                        "term_src": entry["term_src"],
                        "term_tgt": entry["term_tgt"],
                        "node_id": node_id,
                        "node_path": node.get("node_path"),
                        "notes": entry.get("notes") or "",
                        "matched_text": match.group(0),
                    }
                )
        return processed_text, matches

    def _format_glossary_lines(self, entries: Iterable[Dict[str, Any]]) -> str:
        lines = []
        seen: set[int] = set()
        for entry in entries:
            entry_id = entry.get("entry_id") or entry.get("id")
            if entry_id in seen:
                continue
            seen.add(entry_id)
            note = entry.get("notes")
            note_suffix = f" — {note}" if note else ""
            lines.append(f"- {entry.get('term_src')} => {entry.get('term_tgt')}{note_suffix}")
        return "\n".join(lines)

    # ---------------- Doc-level -----------------
    def _build_prompt(
        self,
        body: str,
        source_lang: str,
        target_lang: str,
        mode: str,
        contexto: str | None = None,
        glossary_rules: List[str] | None = None,
    ) -> str:
        lang_name = {
            "en": "English",
            "es": "Spanish",
            "pt": "Portuguese",
        }.get(target_lang, target_lang)
        rules = [
            "Você é um tradutor jurídico. Traduza de Português para " + lang_name + ".",
            "Preserve intactos os marcadores de segmento (<N#>...</N#> no modo doc; <<<NODE:id>>> no modo window).",
            "Preserve tags <ph data-id=\"PHxxxx\"> sem alterar atributos; traduza apenas conteúdo textual interno.",
            "Não explique nada; responda somente com os segmentos traduzidos.",
            "Não crie, remova ou reordene marcadores; mantenha correspondência 1:1.",
        ]
        if glossary_rules:
            unique_rules = list(dict.fromkeys(glossary_rules))
            rules.append(
                "Respeite o glossário obrigatório quando aplicável: " + "; ".join(unique_rules)
            )
        ctx_block = "\nContexto jurídico adicional (RAG):\n" + contexto + "\n" if contexto else ""
        header = "\n".join(["Instruções:"] + [f"- {r}" for r in rules]) + "\n" + ctx_block
        return header + "\nFonte:\n" + body + "\n\nTraduza agora:"
    
    def _linearize(self, nodes: Iterable[Dict]) -> Tuple[str, List[Tuple[int, Dict]]]:
        lines: List[str] = []
        index: List[Tuple[int, Dict]] = []
        for node in nodes:
            try:
                nid = int(node["id"])
            except (KeyError, TypeError, ValueError):
                continue
            content = node.get("_prepared_text")
            if content is None:
                content = node.get("original_text", "")
            lines.append(MARKER_OPEN.format(idx=nid) + content + MARKER_CLOSE.format(idx=nid))
            index.append((nid, node))
        return "".join(lines), index

    @staticmethod
    def _parse_translated(translated: str) -> List[Tuple[int, str]]:
        pattern = re.compile(r"<N(\d+)>\s*(.*?)\s*</N\1>", re.DOTALL)
        return [(int(m.group(1)), m.group(2)) for m in pattern.finditer(translated)]

    def _emit_node_event(self, node: Dict | None, translated_text: str, target_lang: str) -> None:
        if not node:
            return
        try:
            node_id = int(node["id"])
        except (KeyError, TypeError, ValueError):
            return
        # No modo doc/window, não estamos traduzindo por nó aqui.
        # Emitimos NodeMappingEvent para deixar claro que é mapeamento/persistência.
        emit_event(
            NodeMappingEvent(
                node_id=node_id,
                original_text=node.get("original_text", ""),
                translated_text=translated_text,
                source_lang=self.config.source_lang,
                target_lang=target_lang,
                source="doc",
            )
        )

    def _build_rag_context(self, linearized: str, target_lang: str | None) -> str | None:
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
        try:
            items = []
            for s in snippets:
                sid = getattr(s, 'id', None) if hasattr(s, 'id') else (s.get('id') if isinstance(s, dict) else None)
                score = getattr(s, 'score', None) if hasattr(s, 'score') else (s.get('score') if isinstance(s, dict) else None)
                text = getattr(s, 'text', None) if hasattr(s, 'text') else (s.get('text') if isinstance(s, dict) else str(s))
                tags = getattr(s, 'tags', None) if hasattr(s, 'tags') else (s.get('tags') if isinstance(s, dict) else None)
                preview = (text or '')[:280]
                items.append({"id": sid, "score": score, "preview": preview, "tags": tags})
            emit_event(CorpusRetrievalEvent(target_lang=target_lang, items=items))
        except Exception:
            pass
        contexto = Retriever.build_context(snippets, max_chars=rag_cfg.max_context_chars)
        if contexto:
            emit_event(RagContextEvent(context_text=contexto, target_lang=target_lang))
        return contexto

    # ---------------- Validation helpers -----------------
    def _decode_placeholders_payload(self, node: Dict | None) -> Dict[str, Dict]:
        if not node:
            return {}
        raw = node.get("placeholders")
        if not raw:
            return {}
        if isinstance(raw, dict):
            return {k.upper(): v for k, v in raw.items()}
        try:
            loaded = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        if isinstance(loaded, dict):
            return {str(k).upper(): v for k, v in loaded.items()}
        return {}

    def _validate_translation(self, node: Dict | None, translated_text: str) -> None:
        if not node:
            return
        original_text = node.get("original_text", "") or ""
        expected_tokens = _extract_placeholder_tokens(original_text)
        if not expected_tokens:
            return
        translation_tokens = _extract_placeholder_tokens(translated_text)
        mapping = self._decode_placeholders_payload(node)

        missing_mapping = [token for token in translation_tokens if token not in mapping]
        if missing_mapping:
            raise PlaceholderValidationError(
                f"Placeholder inválido no nó {node.get('id')}: tokens desconhecidos {missing_mapping}."
            )

        if Counter(expected_tokens) != Counter(translation_tokens):
            extra = list((Counter(translation_tokens) - Counter(expected_tokens)).elements())
            missing = list((Counter(expected_tokens) - Counter(translation_tokens)).elements())
            raise PlaceholderValidationError(
                f"Placeholders divergentes no nó {node.get('id')}: faltando {missing}, extras {extra}."
            )

        if translation_tokens != expected_tokens:
            raise PlaceholderValidationError(
                f"Ordem de placeholders alterada no nó {node.get('id')}."
            )

        lowered = translated_text.lower()
        idx = lowered.find("ph>")
        while idx != -1:
            prev = lowered[idx - 1] if idx > 0 else ""
            if prev not in ("<", "/"):
                snippet = translated_text[max(0, idx - 20): idx + 10]
                raise PlaceholderValidationError(
                    f"Texto corrompido no nó {node.get('id')}: sequência 'ph>' fora de uma tag (trecho: '{snippet}')."
                )
            idx = lowered.find("ph>", idx + 3)

        if re.search(r"<ph(?!\s+data-id=)", translated_text, flags=re.IGNORECASE):
            raise PlaceholderValidationError(
                f"Tag <ph> sem data-id no nó {node.get('id')}"
            )

        stack: List[str] = []
        for match in PH_TAG_ITER_RE.finditer(translated_text):
            token = match.group(1)
            self_closing = bool(match.group(2)) if match.group(0).lower().startswith("<ph") else False
            if token:
                if self_closing:
                    continue
                stack.append(token.upper())
            else:
                if not stack:
                    raise PlaceholderValidationError(
                        f"Fechamento </ph> sem abertura correspondente no nó {node.get('id')}"
                    )
                stack.pop()
        if stack:
            raise PlaceholderValidationError(
                f"Tags <ph> não fechadas no nó {node.get('id')}"
            )

    def _append_placeholder_error_record(self, record: Dict[str, Any]) -> None:
        paths = getattr(self.config, "paths", None)
        if not paths:
            return
        try:
            log_dir = paths.results_dir / "telemetry"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "placeholder_errors.jsonl"
            with open(log_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _handle_placeholder_error(
        self,
        node: Dict | None,
        translated_text: str,
        error: PlaceholderValidationError,
        target_lang: str,
        mode: str,
    ) -> None:
        node_id = None
        node_path = None
        if node:
            try:
                node_id = int(node.get("id"))
            except (TypeError, ValueError):
                node_id = None
            node_path = node.get("node_path")
        message = str(error)
        record: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "doc_name": self.doc_name,
            "document_id": self.document_id,
            "node_id": node_id,
            "node_path": node_path,
            "mode": mode,
            "target_lang": target_lang,
            "message": message,
        }
        translated_excerpt = (translated_text or "").strip()
        if translated_excerpt:
            record["translated_excerpt"] = translated_excerpt[:250]
        self.placeholder_errors.append(record)
        emit_event(
            PlaceholderErrorEvent(
                doc_name=self.doc_name,
                document_id=self.document_id,
                node_id=node_id,
                node_path=node_path,
                mode=mode,
                target_lang=target_lang,
                message=message,
                translated_excerpt=record.get("translated_excerpt"),
            )
        )
        self._append_placeholder_error_record(record)

    def traduzir_doc(self, nodes: List[Dict], target_lang: str) -> Dict[int, str]:
        """Tradução em nível de documento com uma única chamada.

        Emite:
        - DocLinearizationEvent
        - (opcional) CorpusRetrievalEvent + RagContextEvent
        - DocTranslationEvent (ÚNICO)
        - NodeTranslationEvent por nó (mapeamento/persistência)
        """
        backend = self._ensure_backend()
        self.placeholder_errors.clear()
        self.glossary_match_records.clear()

        prepared_nodes: List[Dict] = []
        aggregated_matches: List[Dict[str, Any]] = []
        for node in nodes:
            node_copy = dict(node)
            processed_text, matches = self._prepare_glossary_for_text(
                node_copy,
                node_copy.get("original_text", ""),
                target_lang,
            )
            if matches:
                aggregated_matches.extend(matches)
            node_copy["_prepared_text"] = processed_text
            prepared_nodes.append(node_copy)

        if self.glossary_enabled and aggregated_matches:
            self.glossary_match_records.extend(aggregated_matches)
            emit_event(
                GlossaryMatchesEvent(
                    target_lang=target_lang,
                    matches=[
                        {
                            "entry_id": m.get("entry_id"),
                            "term_src": m.get("term_src"),
                            "term_tgt": m.get("term_tgt"),
                            "node_id": m.get("node_id"),
                            "node_path": m.get("node_path"),
                            "notes": m.get("notes"),
                        }
                        for m in aggregated_matches
                    ],
                )
            )

        glossary_rules: List[str] = []
        if self.glossary_enabled and aggregated_matches:
            seen_entries: set[int] = set()
            for match in aggregated_matches:
                entry_id = match.get("entry_id")
                if entry_id in seen_entries or entry_id is None:
                    continue
                seen_entries.add(entry_id)
                rule = f"{match.get('term_src')} -> {match.get('term_tgt')}"
                if match.get("notes"):
                    rule += f" (Notas: {match.get('notes')})"
                glossary_rules.append(rule)

        glossary_context = (
            self._format_glossary_lines(aggregated_matches) if self.glossary_enabled and aggregated_matches else ""
        )

        linearized, idx = self._linearize(prepared_nodes)
        mapping_payload: List[Dict[str, object]] = []
        for nid, node in idx:
            mapping_payload.append({"marker": nid, "node_id": nid, "original": node.get("original_text", "")})
        emit_event(DocLinearizationEvent(linearized_text=linearized, mapping=mapping_payload, target_lang=target_lang))

        contexto = self._build_rag_context(linearized, target_lang)
        if glossary_context and self.glossary_enabled:
            contexto = (contexto + "\n\n" + glossary_context) if contexto else glossary_context
        prompt = self._build_prompt(
            linearized,
            self.config.source_lang,
            target_lang,
            mode="doc",
            contexto=contexto,
            glossary_rules=glossary_rules,
        )
        emit_event(
            DocPromptEvent(
                mode="doc",
                source_lang=self.config.source_lang,
                target_lang=target_lang,
                prompt=prompt,
                contexto=contexto,
            )
        )
        translated_all = backend.translate(
            text=prompt,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
            contexto=contexto,
        )
        emit_event(DocTranslationEvent(linearized_text=linearized, translated_text=translated_all, target_lang=target_lang))

        parts = self._parse_translated(translated_all)
        out: Dict[int, str] = {}
        node_lookup = {int(n["id"]): n for n in nodes if isinstance(n.get("id"), (int, str)) and str(n.get("id")).isdigit()}
        for nid, text in parts:
            clean = text.strip()
            node = node_lookup.get(nid)
            if node:
                try:
                    self._validate_translation(node, clean)
                except PlaceholderValidationError as exc:
                    fallback = node.get("original_text", "")
                    self._handle_placeholder_error(node, clean, exc, target_lang, mode="doc")
                    clean = fallback
            out[nid] = clean
            if node:
                self._emit_node_event(node, clean, target_lang)
        return out

    # ---------------- Node -----------------
    def traduzir_node(self, node: Dict, target_lang: str) -> str:
        backend = self._ensure_backend()
        self.placeholder_errors.clear()
        self.glossary_match_records.clear()

        original_text = node.get("original_text", "")
        if not original_text.strip():
            return original_text

        try:
            node_id_int = int(node.get("id")) if node.get("id") is not None else None
        except (TypeError, ValueError):
            node_id_int = None

        processed_text, matches = self._prepare_glossary_for_text(node, original_text, target_lang)
        glossary_rules: List[str] = []
        if self.glossary_enabled and matches:
            self.glossary_match_records.extend(matches)
            emit_event(
                GlossaryMatchesEvent(
                    target_lang=target_lang,
                    matches=[
                        {
                            "entry_id": m.get("entry_id"),
                            "term_src": m.get("term_src"),
                            "term_tgt": m.get("term_tgt"),
                            "node_id": m.get("node_id"),
                            "node_path": m.get("node_path"),
                            "notes": m.get("notes"),
                        }
                        for m in matches
                    ],
                )
            )
            seen: set[int] = set()
            for match in matches:
                entry_id = match.get("entry_id")
                if entry_id in seen or entry_id is None:
                    continue
                seen.add(entry_id)
                rule = f"{match.get('term_src')} -> {match.get('term_tgt')}"
                if match.get("notes"):
                    rule += f" (Notas: {match.get('notes')})"
                glossary_rules.append(rule)
        prompt = self._build_prompt(
            processed_text,
            self.config.source_lang,
            target_lang,
            mode="node",
            glossary_rules=glossary_rules,
        )
        translated = backend.translate(
            text=prompt,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
        )
        clean = translated.strip()
        try:
            self._validate_translation(node, clean)
            emit_event(
                NodeTranslationEvent(
                    node_id=int(node.get("id")),
                    node_path=node.get("node_path"),
                    original_text=original_text,
                    translated_text=clean,
                    target_lang=target_lang,
                    mode="node",
                )
            )
            return clean
        except PlaceholderValidationError as exc:
            self._handle_placeholder_error(node, clean, exc, target_lang, mode="node")
            return original_text

    # ---------------- Window -----------------
    def traduzir_window(self, nodes: Iterable[Dict], target_lang: str) -> Dict[int, str]:
        backend = self._ensure_backend()
        out: Dict[int, str] = {}
        nodes_list = [n for n in nodes]
        self.placeholder_errors.clear()
        self.glossary_match_records.clear()
        for start in range(0, len(nodes_list), max(1, self.window_size)):
            node_group = nodes_list[start : start + max(1, self.window_size)]
            chunks: List[str] = []
            ids: List[int] = []
            group_matches: List[Dict[str, Any]] = []
            for n in node_group:
                try:
                    nid = int(n["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                ids.append(nid)
                text = n.get("original_text", "")
                processed_text, matches = self._prepare_glossary_for_text(n, text, target_lang)
                if matches:
                    self.glossary_match_records.extend(matches)
                    group_matches.extend(matches)
                chunks.append(f"<<<NODE:{nid}>>>\n{processed_text}\n")
            if not chunks:
                continue
            window_text = "".join(chunks)
            glossary_rules: List[str] = []
            if self.glossary_enabled and group_matches:
                seen_entries: set[int] = set()
                for match in group_matches:
                    entry_id = match.get("entry_id")
                    if entry_id in seen_entries or entry_id is None:
                        continue
                    seen_entries.add(entry_id)
                    rule = f"{match.get('term_src')} -> {match.get('term_tgt')}"
                    if match.get("notes"):
                        rule += f" (Notas: {match.get('notes')})"
                    glossary_rules.append(rule)
                emit_event(
                    GlossaryMatchesEvent(
                        target_lang=target_lang,
                        matches=[
                            {
                                "entry_id": m.get("entry_id"),
                                "term_src": m.get("term_src"),
                                "term_tgt": m.get("term_tgt"),
                                "node_id": m.get("node_id"),
                                "node_path": m.get("node_path"),
                                "notes": m.get("notes"),
                            }
                            for m in group_matches
                        ],
                    )
                )
            prompt = self._build_prompt(
                window_text,
                self.config.source_lang,
                target_lang,
                mode="window",
                glossary_rules=glossary_rules,
            )
            translated_window = backend.translate(
                text=prompt,
                source_lang=self.config.source_lang,
                target_lang=target_lang,
            )
            emit_event(
                WindowTranslationEvent(
                    node_ids=ids,
                    window_source=window_text,
                    window_translation=translated_window,
                    target_lang=target_lang,
                )
            )
            # Split por marcador
            lines = translated_window.splitlines()
            current_id: int | None = None
            buff: List[str] = []
            for ln in lines:
                if ln.startswith("<<<NODE:") and ln.endswith(">>>"):
                    if current_id is not None:
                        text_block = "\n".join(buff).strip()
                        node_obj = next((x for x in node_group if str(x.get("id")) == str(current_id)), None)
                        if node_obj:
                            try:
                                self._validate_translation(node_obj, text_block)
                            except PlaceholderValidationError as exc:
                                fallback = node_obj.get("original_text", "")
                                self._handle_placeholder_error(node_obj, text_block, exc, target_lang, mode="window")
                                text_block = fallback
                        out[current_id] = text_block
                        if node_obj:
                            try:
                                nid_int = int(node_obj.get("id"))
                            except Exception:
                                nid_int = current_id
                            emit_event(
                                NodeMappingEvent(
                                    node_id=nid_int,
                                    original_text=node_obj.get("original_text", ""),
                                    translated_text=text_block,
                                    source_lang=self.config.source_lang,
                                    target_lang=target_lang,
                                    source="window",
                                )
                            )
                    try:
                        current_id = int(ln[len("<<<NODE:") : -3])
                    except Exception:
                        current_id = None
                    buff = []
                else:
                    buff.append(ln)
            if current_id is not None:
                text_block = "\n".join(buff).strip()
                node_obj = next((x for x in node_group if str(x.get("id")) == str(current_id)), None)
                if node_obj:
                    try:
                        self._validate_translation(node_obj, text_block)
                    except PlaceholderValidationError as exc:
                        fallback = node_obj.get("original_text", "")
                        self._handle_placeholder_error(node_obj, text_block, exc, target_lang, mode="window")
                        text_block = fallback
                out[current_id] = text_block
                if node_obj:
                    try:
                        nid_int = int(node_obj.get("id"))
                    except Exception:
                        nid_int = current_id
                    emit_event(
                        NodeMappingEvent(
                            node_id=nid_int,
                            original_text=node_obj.get("original_text", ""),
                            translated_text=text_block,
                            source_lang=self.config.source_lang,
                            target_lang=target_lang,
                            source="window",
                        )
                    )
        return out
