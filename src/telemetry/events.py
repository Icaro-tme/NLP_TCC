"""Structured translation telemetry events."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from ..core.config import PipelineConfig, TranslationConfig


def _snapshot_translation_config(cfg: TranslationConfig) -> Dict[str, Any]:
    """Serialize TranslationConfig into primitives for logging."""
    return {
        "model_name": cfg.model_name,
        "device": cfg.device,
        "fp16": cfg.fp16,
        "max_length": cfg.max_length,
        "batch_size": cfg.batch_size,
        "backend": cfg.backend,
        "strategy": cfg.strategy,
        "short_node_merge_chars": cfg.short_node_merge_chars,
    }


def build_config_snapshot(config: PipelineConfig) -> Dict[str, Any]:
    return {
        "translation": _snapshot_translation_config(config.translation),
        "source_lang": config.source_lang,
        "target_langs": list(config.target_langs),
        "seed": config.seed,
    }


@dataclass
class TranslationEvent:
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class SessionStartedEvent(TranslationEvent):
    doc_name: str | None
    mode: str
    backend: str
    config_snapshot: Dict[str, Any]


@dataclass
class SessionFinishedEvent(TranslationEvent):
    doc_name: str | None


@dataclass
class LanguageRunStartedEvent(TranslationEvent):
    doc_name: str
    target_lang: str
    node_count: int
    mode: str
    backend: str


@dataclass
class LanguageRunFinishedEvent(TranslationEvent):
    doc_name: str
    target_lang: str
    translated_nodes: int


@dataclass
class NodeTranslationEvent(TranslationEvent):
    node_id: int
    node_path: str | None
    original_text: str
    translated_text: str
    target_lang: str
    mode: str


@dataclass
class WindowTranslationEvent(TranslationEvent):
    node_ids: List[int]
    window_source: str
    window_translation: str
    target_lang: str


@dataclass
class DocLinearizationEvent(TranslationEvent):
    linearized_text: str
    mapping: List[Dict[str, Any]]
    target_lang: str


@dataclass
class DocTranslationEvent(TranslationEvent):
    linearized_text: str
    translated_text: str
    target_lang: str


@dataclass
class DocSyntacticSplitEvent(TranslationEvent):
    node_ids: Sequence[int]
    raw_text: str
    segments: Sequence[str]
    target_lang: str


@dataclass
class RagContextEvent(TranslationEvent):
    context_text: str
    target_lang: str | None = None
