"""Observers for translation telemetry events."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Dict

from .events import (
    DocLinearizationEvent,
    DocSyntacticSplitEvent,
    DocTranslationEvent,
    LanguageRunFinishedEvent,
    LanguageRunStartedEvent,
    NodeTranslationEvent,
    RagContextEvent,
    SessionFinishedEvent,
    SessionStartedEvent,
    TranslationEvent,
    WindowTranslationEvent,
)


class ConsoleObserver:
    """Print events to stdout in a human-friendly format."""

    def __init__(self, max_width: int = 100, max_text_preview: int = 800) -> None:
        self.max_width = max_width
        self.max_text_preview = max_text_preview

    def handle(self, event: TranslationEvent) -> None:
        if isinstance(event, SessionStartedEvent):
            self._print_header(
                "Sessão iniciada",
                {
                    "Documento": event.doc_name or "(desconhecido)",
                    "Modo": event.mode,
                    "Backend": event.backend,
                    "Config": event.config_snapshot["translation"],
                },
            )
        elif isinstance(event, SessionFinishedEvent):
            self._print_header("Sessão encerrada", {"Documento": event.doc_name or "(desconhecido)"})
        elif isinstance(event, LanguageRunStartedEvent):
            self._print_header(
                "Processando idioma",
                {
                    "Documento": event.doc_name,
                    "Idioma alvo": event.target_lang,
                    "Total de nós": event.node_count,
                    "Modo": event.mode,
                },
            )
        elif isinstance(event, LanguageRunFinishedEvent):
            self._print_header(
                "Idioma finalizado",
                {
                    "Documento": event.doc_name,
                    "Idioma alvo": event.target_lang,
                    "Nós traduzidos": event.translated_nodes,
                },
            )
        elif isinstance(event, NodeTranslationEvent):
            body = {
                "Node": event.node_id,
                "Path": event.node_path,
                "Alvo": event.target_lang,
                "Modo": event.mode,
                "Original": self._preview(event.original_text),
                "Tradução": self._preview(event.translated_text),
            }
            self._print_block("Node traduzido", body)
        elif isinstance(event, WindowTranslationEvent):
            body = {
                "Nós": event.node_ids,
                "Alvo": event.target_lang,
                "Fonte": self._preview(event.window_source),
                "Tradução": self._preview(event.window_translation),
            }
            self._print_block("Janela processada", body)
        elif isinstance(event, DocLinearizationEvent):
            mapping_preview = [
                {
                    "marker": idx,
                    "node": row.get("node_id"),
                    "preview": self._preview(row.get("original", ""), limit=200),
                }
                for idx, row in enumerate(event.mapping)
            ][:10]
            body = {
                "Texto linearizado": self._preview(event.linearized_text),
                "Primeiros índices": mapping_preview,
                "Alvo": event.target_lang,
            }
            self._print_block("Documento linearizado", body)
        elif isinstance(event, DocTranslationEvent):
            body = {
                "Alvo": event.target_lang,
                "Tradução": self._preview(event.translated_text),
            }
            self._print_block("Documento traduzido", body)
        elif isinstance(event, DocSyntacticSplitEvent):
            rows = [f"{nid}: {self._preview(seg, limit=200)}" for nid, seg in zip(event.node_ids, event.segments)]
            body = {
                "Alvo": event.target_lang,
                "Trecho original": self._preview(event.raw_text),
                "Distribuição": rows,
            }
            self._print_block("Divisão sintática", body)
        elif isinstance(event, RagContextEvent):
            body = {
                "Alvo": event.target_lang or "(todos)",
                "Contexto": self._preview(event.context_text),
            }
            self._print_block("Contexto RAG", body)

    def _preview(self, text: str, limit: int | None = None) -> str:
        if limit is None:
            limit = self.max_text_preview
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _print_header(self, title: str, data: Dict[str, object]) -> None:
        print("\n" + "=" * self.max_width)
        print(title.upper())
        for key, value in data.items():
            self._print_line(key, value)
        print("=" * self.max_width)

    def _print_block(self, title: str, data: Dict[str, object]) -> None:
        print("\n" + "-" * self.max_width)
        print(f"{title}:")
        for key, value in data.items():
            self._print_line(key, value)

    def _print_line(self, key: str, value: object) -> None:
        if isinstance(value, (list, tuple)):
            print(f"  {key}: {value}")
            return
        if isinstance(value, dict):
            print(f"  {key}:")
            for sub_key, sub_val in value.items():
                wrapped = textwrap.fill(str(sub_val), self.max_width - 6)
                print(f"      {sub_key}: {wrapped}")
            return
        wrapped = textwrap.fill(str(value), self.max_width - 4)
        print(f"  {key}: {wrapped}")


class JsonlObserver:
    """Persist events as JSON lines for later analysis."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def handle(self, event: TranslationEvent) -> None:
        payload = self._serialize_event(event)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _serialize_event(self, event: TranslationEvent) -> Dict[str, object]:
        data: Dict[str, object] = {
            "event_type": event.__class__.__name__,
            "timestamp": getattr(event, "timestamp", None),
        }
        for key, value in event.__dict__.items():
            if key == "timestamp":
                continue
            data[key] = value
        return data
