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
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

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
)
from ..rag.retriever import Retriever


MARKER_OPEN = "<N{idx}>"
MARKER_CLOSE = "</N{idx}>"


@dataclass
class ServicoTraducao:
    config: PipelineConfig
    backend: GoogleLLMBackend | None = None
    window_size: int = 3

    # ---------------- Backend -----------------
    def _ensure_backend(self) -> GoogleLLMBackend:
        if self.backend:
            return self.backend
        self.backend = GoogleLLMBackend()
        return self.backend

    # ---------------- Doc-level -----------------
    def _build_prompt(self, body: str, source_lang: str, target_lang: str, mode: str, contexto: str | None = None) -> str:
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

    def traduzir_doc(self, nodes: List[Dict], target_lang: str) -> Dict[int, str]:
        """Tradução em nível de documento com uma única chamada.

        Emite:
        - DocLinearizationEvent
        - (opcional) CorpusRetrievalEvent + RagContextEvent
        - DocTranslationEvent (ÚNICO)
        - NodeTranslationEvent por nó (mapeamento/persistência)
        """
        backend = self._ensure_backend()
        linearized, idx = self._linearize(nodes)
        mapping_payload: List[Dict[str, object]] = []
        for nid, node in idx:
            mapping_payload.append({"marker": nid, "node_id": nid, "original": node.get("original_text", "")})
        emit_event(DocLinearizationEvent(linearized_text=linearized, mapping=mapping_payload, target_lang=target_lang))

        contexto = self._build_rag_context(linearized, target_lang)
        prompt = self._build_prompt(linearized, self.config.source_lang, target_lang, mode="doc", contexto=contexto)
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
            out[nid] = clean
            self._emit_node_event(node_lookup.get(nid), clean, target_lang)
        return out

    # ---------------- Node -----------------
    def traduzir_node(self, node: Dict, target_lang: str) -> str:
        backend = self._ensure_backend()
        original_text = node.get("original_text", "")
        if not original_text.strip():
            return original_text
        prompt = self._build_prompt(original_text, self.config.source_lang, target_lang, mode="node")
        translated = backend.translate(
            text=prompt,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
        )
        emit_event(
            NodeTranslationEvent(
                node_id=int(node.get("id")),
                node_path=node.get("node_path"),
                original_text=original_text,
                translated_text=translated,
                target_lang=target_lang,
                mode="node",
            )
        )
        return translated

    # ---------------- Window -----------------
    def traduzir_window(self, nodes: Iterable[Dict], target_lang: str) -> Dict[int, str]:
        backend = self._ensure_backend()
        out: Dict[int, str] = {}
        nodes_list = [n for n in nodes]
        for start in range(0, len(nodes_list), max(1, self.window_size)):
            node_group = nodes_list[start : start + max(1, self.window_size)]
            chunks: List[str] = []
            ids: List[int] = []
            for n in node_group:
                try:
                    nid = int(n["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                ids.append(nid)
                text = n.get("original_text", "")
                chunks.append(f"<<<NODE:{nid}>>>\n{text}\n")
            if not chunks:
                continue
            window_text = "".join(chunks)
            prompt = self._build_prompt(window_text, self.config.source_lang, target_lang, mode="window")
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
                        out[current_id] = text_block
                        node_obj = next((x for x in node_group if str(x.get("id")) == str(current_id)), None)
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
                out[current_id] = text_block
                node_obj = next((x for x in node_group if str(x.get("id")) == str(current_id)), None)
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
