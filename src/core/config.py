"""Configuration dataclasses centralizing runtime options for the MVP pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class TranslationConfig:
    """Low-level configuration for machine translation execution."""

    model_name: str = "facebook/m2m100_418M"
    device: str = "auto"  # "auto", "cuda", "cpu"
    fp16: bool = False
    max_length: int = 1024
    batch_size: int = 1
    use_device_map: bool = True
    trust_remote_code: bool = False
    backend: str = "hf"  # hf | google
    strategy: str = "node"  # node | window | doc
    short_node_merge_chars: int = 10  # threshold for doc-level merging heuristic


@dataclass(frozen=True)
class PathsConfig:
    """Absolute or project-relative paths used across the pipeline."""

    project_root: Path
    data_dir: Path
    db_path: Path
    glossario_dir: Path
    corpus_dir: Path
    results_dir: Path


@dataclass(frozen=True)
class PipelineConfig:
    """High-level aggregation of all configuration knobs for the MVP."""

    translation: TranslationConfig = field(default_factory=TranslationConfig)
    paths: PathsConfig | None = None
    source_lang: str = "pt"
    target_langs: List[str] = field(default_factory=lambda: ["en", "es"])
    seed: Optional[int] = 42
