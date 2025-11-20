"""Context helpers for enabling translation telemetry."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable

from ..core.config import PipelineConfig
from .bus import emit_event, event_bus
from .events import (
    LanguageRunFinishedEvent,
    LanguageRunStartedEvent,
    SessionFinishedEvent,
    SessionStartedEvent,
    build_config_snapshot,
)
from .observer import ConsoleObserver, JsonlObserver


@contextmanager
def translation_observer(
    enabled: bool,
    config: PipelineConfig,
    mode: str,
    backend: str,
    doc_name: str | None,
    target_langs: Iterable[str],
    jsonl_path: str | None = None,
    console: bool = True,
):
    observers = []
    if enabled:
        if console:
            console_observer = ConsoleObserver()
            observers.append(console_observer)
            event_bus.register(console_observer.handle)
        if jsonl_path:
            jsonl_observer = JsonlObserver(jsonl_path)
            observers.append(jsonl_observer)
            event_bus.register(jsonl_observer.handle)
        emit_event(
            SessionStartedEvent(
                doc_name=doc_name,
                mode=mode,
                backend=backend,
                config_snapshot=build_config_snapshot(config),
            )
        )
    try:
        yield
    finally:
        if enabled and observers:
            emit_event(SessionFinishedEvent(doc_name=doc_name))
            for obs in observers:
                event_bus.unregister(obs.handle)


def emit_language_start(
    enabled: bool,
    doc_name: str,
    target_lang: str,
    mode: str,
    backend: str,
    node_count: int,
) -> None:
    if not enabled:
        return
    emit_event(
        LanguageRunStartedEvent(
            doc_name=doc_name,
            target_lang=target_lang,
            node_count=node_count,
            mode=mode,
            backend=backend,
        )
    )


def emit_language_finish(enabled: bool, doc_name: str, target_lang: str, translated_nodes: int) -> None:
    if not enabled:
        return
    emit_event(
        LanguageRunFinishedEvent(
            doc_name=doc_name,
            target_lang=target_lang,
            translated_nodes=translated_nodes,
        )
    )
