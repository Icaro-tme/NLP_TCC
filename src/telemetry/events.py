"""Eventos de telemetria de tradução estruturados.

Documentação e nomes em português conforme diretrizes do projeto.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Optional

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
class NodeMappingEvent(TranslationEvent):
    """Evento de mapeamento/persistência por nó a partir de uma tradução
    em nível de documento ou janela. Não representa tradução por nó.

    Use `source` para indicar a origem ("doc" ou "window").
    """

    node_id: int
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    source: str  # "doc" ou "window"


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
class DocPromptEvent(TranslationEvent):
    """Evento para logar o Prompt completo utilizado na tradução.

    Preferencialmente emitido no modo documento (doc). Pode ser usado
    em outros modos conforme necessidade.
    """

    mode: str  # "doc" | "node" | "window"
    source_lang: str
    target_lang: str
    prompt: str
    contexto: Optional[str] = None


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


@dataclass
class CorpusRetrievalEvent(TranslationEvent):
    """Eventos detalhando os trechos recuperados do Corpus (RAG)."""
    target_lang: str | None
    items: List[Dict[str, Any]]  


@dataclass
class GlossaryMatchesEvent(TranslationEvent):
    """Eventos relatando quais termos do glossário foram detectados no texto de origem."""
    target_lang: str | None
    matches: List[Dict[str, Any]] 


# Eventos opcionais de Prompt por nó/janela
# Para habilitar, basta emitir estes eventos no pipeline.
@dataclass
class NodePromptEvent(TranslationEvent):
    node_id: int
    source_lang: str
    target_lang: str
    prompt: str


@dataclass
class WindowPromptEvent(TranslationEvent):
    window_index: int
    node_ids: List[int]
    source_lang: str
    target_lang: str
    prompt: str
