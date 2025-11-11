"""Command line entry point orchestrating the MVP workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List


# Ensure project root (parent of scripts/) is on the import path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Lightweight .env loader (avoids external dependency). We only set variables not already set.
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, raw_val = line.split("=", 1)
        key = key.strip()
        val = raw_val.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = val


from src.core.config import PathsConfig, PipelineConfig, TranslationConfig
from src.core.logging_utils import get_logger, log_time
from src.dom_indexer import index_html
from src.html_io import read_html, write_html
from src.persistence.db import Database
from src.persistence.repos import DocumentRepository, NodeRepository
from src.services.export_service import ExportService
from src.services.translation_service import TranslationService
from src.services.doc_level_service import DocLevelTranslationService
from src.translate import TranslationGateway


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NLP TCC MVP CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest HTML and index nodes")
    ingest_parser.add_argument("--input", required=True, help="Path to the HTML file")
    ingest_parser.add_argument(
        "--languages",
        default="en",
        help="Comma-separated list of target languages (default: en)",
    )
    ingest_parser.add_argument("--source-lang", default="pt", help="Source language code")
    ingest_parser.set_defaults(func=handle_ingest)

    process_parser = subparsers.add_parser("process", help="Ingest and translate document")
    process_parser.add_argument("--input", required=True, help="Path to the HTML file")
    process_parser.add_argument(
        "--languages",
        default="en",
        help="Comma-separated list of target languages",
    )
    process_parser.add_argument("--source-lang", default="pt", help="Source language code")
    process_parser.add_argument("--device", default="auto", help="Device override (auto|cuda|cpu)")
    process_parser.add_argument("--fp16", action="store_true", help="Enable fp16 when supported")
    process_parser.add_argument(
        "--mode",
        choices=["node", "window", "doc"],
        default="node",
        help="Translation strategy: node (isolated), window (grouped context), doc (linearize whole document)",
    )
    process_parser.add_argument(
        "--backend",
        choices=["hf", "google"],
        default="hf",
        help="Translation backend: HuggingFace (hf) or Google Gemini (google)",
    )
    process_parser.set_defaults(func=handle_process)

    export_parser = subparsers.add_parser("export", help="Export translated HTML variant")
    export_parser.add_argument("--doc", required=True, help="Base document name (without lang suffix)")
    export_parser.add_argument("--language", required=True, help="Target language code")
    export_parser.add_argument(
        "--variant",
        choices=["baseline", "adapted", "human"],
        default="adapted",
        help="Variant to export",
    )
    export_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit output path",
    )
    export_parser.add_argument("--source-lang", default="pt", help="Source language code")
    export_parser.set_defaults(func=handle_export)

    return parser.parse_args()


def build_pipeline_config(args: argparse.Namespace) -> PipelineConfig:
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    glossary_dir = project_root / "glossario"
    if hasattr(args, "languages"):
        target_langs = _parse_languages(args.languages)
    elif hasattr(args, "language"):
        target_langs = [args.language]
    else:
        target_langs = ["en"]

    config = PipelineConfig(
        translation=TranslationConfig(
            device=args.device if hasattr(args, "device") else "auto",
            fp16=bool(getattr(args, "fp16", False)),
            backend=getattr(args, "backend", "hf"),
            strategy=getattr(args, "mode", "node"),
        ),
        source_lang=args.source_lang,
        target_langs=target_langs,
        paths=PathsConfig(
            project_root=project_root,
            data_dir=data_dir,
            db_path=data_dir / "db" / "nlp_tcc.sqlite",
            glossario_dir=glossary_dir,
            corpus_dir=project_root / "corpus",
            results_dir=project_root / "results",
        ),
    )
    return config


def handle_ingest(args: argparse.Namespace) -> None:
    config = build_pipeline_config(args)
    logger = get_logger()
    results = _ingest_internal(config, Path(args.input), logger)
    logger.info(
        "Ingested document '%s' with %d nodes", results["doc_name"], results["node_count"]
    )


def handle_process(args: argparse.Namespace) -> None:
    config = build_pipeline_config(args)
    logger = get_logger()
    ingest_result = _ingest_internal(config, Path(args.input), logger)
    db = Database(config.paths.db_path)
    node_repo = NodeRepository(db)
    # Novo serviço permite modos diferentes; parâmetro futuro via CLI.
    translation_service = TranslationService(config=config)
    translation_service.mode = args.mode
    doc_service = DocLevelTranslationService(config=config)
    translations_per_lang: Dict[str, int] = {}
    for lang, document_id in ingest_result["document_ids"].items():
        nodes = node_repo.list_nodes(document_id)
        translated_count = 0
        # Estratégia híbrida: janela se benefício de contexto, senão fallback nó-a-nó.
        if args.mode == "doc":
            # Document-level translation with linearization markers.
            id_to_translation = doc_service.translate_document(nodes, target_lang=lang)
            for node in nodes:
                translated_text = id_to_translation.get(node["id"]) or node.get("original_text", "")
                node_repo.save_translation(node_id=node["id"], translation=translated_text)
                translated_count += 1
        elif translation_service.mode == "window":
            id_to_translation = translation_service.translate_nodes_windowed(nodes, target_lang=lang)
            for node in nodes:
                translated_text = id_to_translation.get(node["id"]) or translation_service.translate_node(node, target_lang=lang)
                node_repo.save_translation(node_id=node["id"], translation=translated_text)
                translated_count += 1
        else:
            for node in nodes:
                with log_time(logger, f"translate node {node['node_path']} -> {lang}"):
                    translated_text = translation_service.translate_node(node, target_lang=lang)
                    node_repo.save_translation(node_id=node["id"], translation=translated_text)
                    translated_count += 1
        translations_per_lang[lang] = translated_count
    for lang, count in translations_per_lang.items():
        logger.info("Translated %d nodes for language %s", count, lang)


def handle_export(args: argparse.Namespace) -> None:
    config = build_pipeline_config(args)
    logger = get_logger()
    db = Database(config.paths.db_path)
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)
    document_id = doc_repo.find_document_id(args.doc, args.source_lang, args.language)
    if document_id is None:
        raise SystemExit(
            f"Document {args.doc} ({args.source_lang}->{args.language}) not found. Ingest/process first."
        )
    nodes = node_repo.list_nodes(document_id)
    extracted_dir = config.paths.data_dir / "extracted"
    html_path = extracted_dir / f"{args.doc}_indexed.html"
    if not html_path.exists():
        raise SystemExit(f"Indexed HTML not found at {html_path}. Run ingest/process again.")
    original_html = read_html(html_path)
    export_service = ExportService()
    output_path = args.output or (
        config.paths.results_dir
        / "html"
        / f"{args.doc}_{args.variant}_{args.language}.html"
    )
    logger.info("Exporting %s variant for %s -> %s", args.variant, args.doc, args.language)
    export_service.export_variant(
        original_html=original_html,
        nodes=_inflate_nodes(nodes),
        variant=args.variant,
        output_path=output_path,
    )
    logger.info("Wrote %s", output_path)


def _ingest_internal(
    config: PipelineConfig, input_path: Path, logger
) -> Dict[str, object]:
    html = read_html(input_path)
    indexed_html, nodes = index_html(html)
    extracted_dir = config.paths.data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    doc_name = input_path.stem
    indexed_path = extracted_dir / f"{doc_name}_indexed.html"
    write_html(indexed_path, indexed_html)
    sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    db = Database(config.paths.db_path)
    db.init_schema()
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)
    document_ids: Dict[str, int] = {}
    for target_lang in config.target_langs:
        document_id = doc_repo.upsert_document(
            name=doc_name,
            lang_src=config.source_lang,
            lang_tgt=target_lang,
            sha256=sha256,
        )
        node_repo.delete_nodes_by_document(document_id)
        node_repo.insert_nodes(document_id, nodes)
        document_ids[target_lang] = document_id
    return {
        "doc_name": doc_name,
        "indexed_path": indexed_path,
        "node_count": len(nodes),
        "document_ids": document_ids,
    }


def _inflate_nodes(rows: List[dict]) -> List[dict]:
    inflated = []
    for row in rows:
        placeholders = row.get("placeholders")
        if isinstance(placeholders, str):
            placeholders = json.loads(placeholders)
        inflated.append({**row, "placeholders": placeholders})
    return inflated


def _parse_languages(raw: str) -> List[str]:
    return [lang.strip() for lang in raw.split(",") if lang.strip()]


if __name__ == "__main__":
    args = parse_args()
    args.func(args)
