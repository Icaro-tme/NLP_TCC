from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..core.config import PathsConfig, PipelineConfig, TranslationConfig
from ..persistence.db import Database
from ..persistence.repos import DocumentRepository, NodeRepository
from ..persistence.rag_repos import CorpusRepository, GlossaryRepository
from ..services.doc_level_service import DocLevelTranslationService
from ..services.translation_service import TranslationService
from ..services.export_service import ExportService
from ..services.text_export_service import TextExportService
from ..html_io import read_html
from ..rag.utils import invalidate_rag_index


app = FastAPI(title="NLP TCC API", version="0.1")


def build_paths() -> PathsConfig:
    project_root = Path(__file__).resolve().parents[2]
    paths = PathsConfig(
        project_root=project_root,
        data_dir=project_root / "data",
        db_path=project_root / "data" / "db" / "nlp_tcc.sqlite",
        glossario_dir=project_root / "glossario",
        corpus_dir=project_root / "corpus",
        results_dir=project_root / "results",
    )
    return paths


class ProcessRequest(BaseModel):
    input: str
    language: str = "en"
    source_lang: str = "pt"
    backend: str = "google"  # hf|google
    mode: str = "doc"  # node|window|doc


class GlossaryFeedbackRequest(BaseModel):
    source: str
    target: str
    source_lang: str = "pt"
    target_lang: str = "en"
    notes: str | None = None


class CorpusFeedbackRequest(BaseModel):
    text: str
    language: str = "pt"
    tags: list[str] | None = None
    notes: str | None = None


class HumanTranslationRequest(BaseModel):
    translation: str
    overwrite_adapted: bool = False
    context: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/process")
def process(req: ProcessRequest):
    cfg = PipelineConfig(
        translation=TranslationConfig(
            backend=req.backend,
            strategy=req.mode,
        ),
        paths=build_paths(),
        source_lang=req.source_lang,
        target_langs=[req.language],
    )
    db = Database(cfg.paths.db_path)
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)

    # Minimal ingest reuse (mirror of CLI):
    from ..html_io import read_html, write_html
    from ..dom_indexer import index_html
    html = read_html(Path(req.input))
    indexed_html, nodes = index_html(html)
    extracted_dir = cfg.paths.data_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    doc_name = Path(req.input).stem
    write_html(extracted_dir / f"{doc_name}_indexed.html", indexed_html)
    document_id = doc_repo.upsert_document(doc_name, cfg.source_lang, req.language, None)
    node_repo.delete_nodes_by_document(document_id)
    node_repo.insert_nodes(document_id, nodes)

    # Translation
    if req.mode == "doc":
        doc_service = DocLevelTranslationService(config=cfg)
        id_to_translation = doc_service.translate_document(node_repo.list_nodes(document_id), target_lang=req.language)
        context_used = doc_service.last_context
        for node in node_repo.list_nodes(document_id):
            txt = id_to_translation.get(node["id"]) or node.get("original_text", "")
            node_repo.save_translation(node_id=node["id"], translation=txt, context=context_used)
    else:
        ts = TranslationService(config=cfg)
        ts.mode = req.mode
        for node in node_repo.list_nodes(document_id):
            txt = ts.translate_node(node, target_lang=req.language)
            node_repo.save_translation(node_id=node["id"], translation=txt)
    return {"document": doc_name, "language": req.language, "nodes": len(nodes)}


@app.post("/feedback/glossary")
def feedback_glossary(req: GlossaryFeedbackRequest):
    paths = build_paths()
    db = Database(paths.db_path)
    gloss_repo = GlossaryRepository(db)
    gloss_repo.add_entry(
        term_src=req.source,
        lang_src=req.source_lang,
        term_tgt=req.target,
        lang_tgt=req.target_lang,
        notes=req.notes,
    )
    invalidate_rag_index(paths)
    return {"status": "recorded"}


@app.post("/feedback/corpus")
def feedback_corpus(req: CorpusFeedbackRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="campo 'text' não pode estar vazio")
    paths = build_paths()
    db = Database(paths.db_path)
    corpus_repo = CorpusRepository(db)
    corpus_repo.add_snippet(
        text=req.text,
        language=req.language,
        tags=req.tags or [],
        notes=req.notes,
    )
    invalidate_rag_index(paths)
    return {"status": "recorded"}


@app.post("/nodes/{node_id}/human-translation")
def set_human_translation(node_id: int, req: HumanTranslationRequest):
    paths = build_paths()
    db = Database(paths.db_path)
    node_repo = NodeRepository(db)
    node = node_repo.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="nó não encontrado")
    node_repo.save_human_translation(
        node_id=node_id,
        translation=req.translation,
        overwrite_adapted=req.overwrite_adapted,
        context=req.context,
    )
    return {"node_id": node_id, "status": "updated"}


class ExportRequest(BaseModel):
    doc: str
    language: str
    variant: str = "adapted"
    source_lang: str = "pt"


@app.post("/export/html")
def export_html(req: ExportRequest):
    paths = build_paths()
    db = Database(paths.db_path)
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)
    document_id = doc_repo.find_document_id(req.doc, req.source_lang, req.language)
    if not document_id:
        return {"error": "document not found"}
    nodes = node_repo.list_nodes(document_id)
    html_path = paths.data_dir / "extracted" / f"{req.doc}_indexed.html"
    original_html = read_html(html_path)
    out = paths.results_dir / "html" / f"{req.doc}_{req.variant}_{req.language}.html"
    ExportService().export_variant(original_html, nodes, req.variant, out)
    return {"output": str(out)}


@app.post("/export/text")
def export_text(req: ExportRequest):
    paths = build_paths()
    db = Database(paths.db_path)
    doc_repo = DocumentRepository(db)
    node_repo = NodeRepository(db)
    document_id = doc_repo.find_document_id(req.doc, req.source_lang, req.language)
    if not document_id:
        return {"error": "document not found"}
    nodes = node_repo.list_nodes(document_id)
    html_path = paths.data_dir / "extracted" / f"{req.doc}_indexed.html"
    original_html = read_html(html_path)
    out = paths.results_dir / "text" / f"{req.doc}_{req.variant}_{req.language}.txt"
    TextExportService().export_variant_text(original_html, nodes, req.variant, out)
    return {"output": str(out)}
