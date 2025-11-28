from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .base_controller import BaseController
from ...core.config import PipelineConfig, TranslationConfig, PathsConfig, RagConfig
from ...persistence.db import Database
from ...persistence.repos import DocumentRepository, NodeRepository
from ...services.doc_level_service import DocLevelTranslationService
from ...services.translation_service import TranslationService
from ..models.process_models import ProcessRequest
from ...services.export_service import ExportService

class ProcessController(BaseController):
    def __init__(self, paths: PathsConfig):
        # Endpoint de pipeline completo em português
        super().__init__(prefix="/processar", tags=["processo"])
        self.paths = paths
        r = self.router

        @r.post(
            "",
            summary="Processar documento (pipeline completo)",
            description=(
                "Executa a ingestão do HTML, indexação em nós e tradução conforme modo selecionado "
                "(ex.: doc). Persiste nós e traduções no banco."
            ),
        )
        def processar(req: ProcessRequest):
            # Configuração base (sem RAG) para baseline
            cfg_baseline = PipelineConfig(
                translation=TranslationConfig(
                    backend=req.backend,
                    strategy=req.mode,
                ),
                paths=self.paths,
                source_lang=req.source_lang,
                target_langs=[req.language],
                rag=None,
            )
            # Configuração adaptada (com RAG) se solicitado
            cfg_adapt: PipelineConfig | None = None
            if req.rag_topk > 0 and req.mode == "doc":
                cfg_adapt = PipelineConfig(
                    translation=TranslationConfig(
                        backend=req.backend,
                        strategy=req.mode,
                    ),
                    paths=self.paths,
                    source_lang=req.source_lang,
                    target_langs=[req.language],
                    rag=RagConfig(top_k=req.rag_topk, index_dir=self.paths.data_dir / "rag_index", enabled=True),
                )
            db = Database(cfg_baseline.paths.db_path)
            doc_repo = DocumentRepository(db)
            node_repo = NodeRepository(db)
            from ...html_io import read_html, write_html
            from ...dom_indexer import index_html
            input_path = Path(req.input)
            if not input_path.is_absolute():
                input_path = self.paths.project_root / input_path
            if not input_path.exists():
                raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {input_path}")
            html = read_html(input_path)
            indexed_html, nodes = index_html(html)
            extracted_dir = cfg_baseline.paths.data_dir / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            doc_name = Path(req.input).stem
            write_html(extracted_dir / f"{doc_name}_indexed.html", indexed_html)
            document_id = doc_repo.upsert_document(doc_name, cfg_baseline.source_lang, req.language, None)
            node_repo.delete_nodes_by_document(document_id)
            node_repo.insert_nodes(document_id, nodes)
            if req.mode == "doc":
                # Passo baseline (sem RAG)
                doc_service_base = DocLevelTranslationService(config=cfg_baseline)
                baseline_map = doc_service_base.translate_document(node_repo.list_nodes(document_id), target_lang=req.language)
                for node in node_repo.list_nodes(document_id):
                    txt_base = baseline_map.get(node["id"]) or node.get("original_text", "")
                    node_repo.save_baseline(node_id=node["id"], translation=txt_base)
                # Passo adaptado (com RAG) se configurado
                if cfg_adapt is not None:
                    doc_service_adapt = DocLevelTranslationService(config=cfg_adapt)
                    adapted_map = doc_service_adapt.translate_document(node_repo.list_nodes(document_id), target_lang=req.language)
                    context_used = doc_service_adapt.last_context
                    for node in node_repo.list_nodes(document_id):
                        txt_adapt = adapted_map.get(node["id"]) or node.get("original_text", "")
                        node_repo.save_adapted(node_id=node["id"], translation=txt_adapt, context=context_used)
                else:
                    # Se não há RAG, consideramos baseline também como adapted para compatibilidade
                    for node in node_repo.list_nodes(document_id):
                        node_repo.save_adapted(node_id=node["id"], translation=node_repo.get_node(node["id"]).get("baseline_text", ""), context="")
            else:
                ts = TranslationService(config=cfg_baseline)
                ts.mode = req.mode
                for node in node_repo.list_nodes(document_id):
                    txt = ts.translate_node(node, target_lang=req.language)
                    node_repo.save_translation(node_id=node["id"], translation=txt)
            
            # Recupera nós atualizados do banco (com as traduções recém-salvas)
            final_nodes = node_repo.list_nodes(document_id)
            results_html_dir = self.paths.results_dir / "html"
            results_html_dir.mkdir(parents=True, exist_ok=True)

            exporter = ExportService()
            
            # Exporta Baseline
            out_baseline = results_html_dir / f"{doc_name}_baseline_{req.language}.html"
            exporter.export_variant(indexed_html, final_nodes, "baseline", out_baseline)

            # Exporta Adapted (sempre gerado, mesmo que igual ao baseline se sem RAG)
            out_adapted = results_html_dir / f"{doc_name}_adapted_{req.language}.html"
            exporter.export_variant(indexed_html, final_nodes, "adapted", out_adapted)

            return {
                "documento": doc_name,
                "idioma": req.language,
                "nos": len(nodes),
                "rag_topk": req.rag_topk,
                "adaptado": bool(cfg_adapt is not None),
            }
