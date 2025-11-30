from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json

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
            # Validação: apenas backend Google é suportado agora (campo de backend removido do modelo).
            # Modos suportados: doc, doc-sintatico, node, window (todos via backend Google).
            # Configuração base (sem RAG) para baseline
            cfg_baseline = PipelineConfig(
                translation=TranslationConfig(
                    backend="google",
                    strategy=req.mode,
                ),
                paths=self.paths,
                source_lang=req.source_lang,
                target_langs=[req.language],
                rag=None,
            )
            # Configuração adaptada (com RAG) se solicitado
            cfg_adapt: PipelineConfig | None = None
            if req.rag_topk > 0:
                cfg_adapt = PipelineConfig(
                    translation=TranslationConfig(
                        backend="google",
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
                # Modos node/window com dual-pass quando RAG ativo
                ts_base = TranslationService(config=cfg_baseline)
                ts_base.mode = req.mode
                ts_adapt = None
                if cfg_adapt is not None:
                    ts_adapt = TranslationService(config=cfg_adapt)
                    ts_adapt.mode = req.mode
                if req.mode == "window":
                    # Tradução por janela
                    from ...segmentation import build_windows, split_window_translation
                    windows = build_windows(node_repo.list_nodes(document_id))
                    # Baseline por janela
                    backend_base = ts_base._ensure_backend()
                    backend_adapt = ts_adapt._ensure_backend() if ts_adapt else None
                    contexto_payload = None
                    # Preparar retriever uma vez
                    retriever = None
                    if ts_adapt and ts_adapt.config.rag:
                        from ...rag.retriever import Retriever
                        index_dir = ts_adapt.config.rag.index_dir or (ts_adapt.config.paths.data_dir / "rag_index")
                        retriever = Retriever(model_name=ts_adapt.config.rag.model, index_dir=index_dir, db_path=ts_adapt.config.paths.db_path)
                        if not retriever.has_index():
                            retriever.build_index()
                    for node_group, window_text in windows:
                        baseline_window = backend_base.translate(window_text, source_lang=req.source_lang, target_lang=req.language)
                        adapted_window = baseline_window
                        if ts_adapt and retriever:
                            query_text = window_text[:2000]
                            snippets = retriever.retrieve(query_text, top_k=ts_adapt.config.rag.top_k, source_lang=req.source_lang, target_lang=req.language)
                            from ...rag.retriever import Retriever as _R
                            contexto_payload = _R.build_context(snippets, max_chars=ts_adapt.config.rag.max_context_chars)
                            adapted_window = backend_adapt.translate(window_text, source_lang=req.source_lang, target_lang=req.language, contexto=contexto_payload)
                        base_splits = split_window_translation(baseline_window)
                        adapt_splits = split_window_translation(adapted_window)
                        base_lookup = {nid: txt for nid, txt in base_splits}
                        adapt_lookup = {nid: txt for nid, txt in adapt_splits}
                        for n in node_group:
                            nid_str = str(n["id"])
                            btxt = base_lookup.get(nid_str, n.get("original_text", ""))
                            atxt = adapt_lookup.get(nid_str, btxt)
                            node_repo.save_baseline(node_id=n["id"], translation=btxt)
                            node_repo.save_adapted(node_id=n["id"], translation=atxt, context=contexto_payload)
                else:
                    # Modo node: processa nó a nó
                    backend_base = ts_base._ensure_backend()
                    backend_adapt = ts_adapt._ensure_backend() if ts_adapt else None
                    retriever = None
                    if ts_adapt and ts_adapt.config.rag:
                        from ...rag.retriever import Retriever
                        index_dir = ts_adapt.config.rag.index_dir or (ts_adapt.config.paths.data_dir / "rag_index")
                        retriever = Retriever(model_name=ts_adapt.config.rag.model, index_dir=index_dir, db_path=ts_adapt.config.paths.db_path)
                        if not retriever.has_index():
                            retriever.build_index()
                    for node in node_repo.list_nodes(document_id):
                        src = node.get("original_text", "")
                        btxt = backend_base.translate(src, source_lang=req.source_lang, target_lang=req.language) if src.strip() else src
                        atxt = btxt
                        contexto_payload = None
                        if backend_adapt and retriever and src.strip():
                            query_text = src[:1000]
                            snippets = retriever.retrieve(query_text, top_k=ts_adapt.config.rag.top_k, source_lang=req.source_lang, target_lang=req.language)
                            from ...rag.retriever import Retriever as _R
                            contexto_payload = _R.build_context(snippets, max_chars=ts_adapt.config.rag.max_context_chars)
                            atxt = backend_adapt.translate(src, source_lang=req.source_lang, target_lang=req.language, contexto=contexto_payload)
                        node_repo.save_baseline(node_id=node["id"], translation=btxt)
                        node_repo.save_adapted(node_id=node["id"], translation=atxt, context=contexto_payload)
            
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
                "modo": req.mode,
                "backend": "google",
            }

        # SSE: stream de eventos de telemetria em tempo real
        from ...telemetry.bus import event_bus
        from ...telemetry.events import TranslationEvent

        @r.get(
            "/eventos",
            summary="Stream de eventos (SSE)",
            description="Conecta-se ao barramento de telemetria e envia eventos em tempo real via Server-Sent Events.",
        )
        async def eventos_sse():
            queue: asyncio.Queue[str] = asyncio.Queue()

            def handler(event: TranslationEvent) -> None:
                try:
                    payload = {k: v for k, v in event.__dict__.items() if k != "timestamp"}
                    payload["event_type"] = event.__class__.__name__
                    data = json.dumps(payload, ensure_ascii=False)
                    queue.put_nowait(f"data: {data}\n\n")
                except Exception:
                    # Evita que erros do handler quebrem o fluxo principal
                    pass

            event_bus.register(handler)

            async def event_generator():
                try:
                    # Mensagem inicial para confirmar conexão
                    yield "event: open\n" + "data: conectado\n\n"
                    while True:
                        chunk = await queue.get()
                        yield chunk
                except asyncio.CancelledError:
                    # Cliente desconectou
                    pass
                finally:
                    event_bus.unregister(handler)

            return StreamingResponse(event_generator(), media_type="text/event-stream")
