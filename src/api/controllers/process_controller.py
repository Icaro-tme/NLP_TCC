from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
from ...telemetry.bus import event_bus
from ...telemetry.events import TranslationEvent

from .base_controller import BaseController
from ...core.config import PipelineConfig, TranslationConfig, PathsConfig, RagConfig
from ...persistence.db import Database
from ...persistence.repos import DocumentRepository, NodeRepository
from ...services.translation_pipeline import ServicoTraducao
from ..models.process_models import ProcessRequest
from ...services.export_service import HTMLExportService

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
            # Apenas backend Google é suportado; modos: doc, node, window
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
                self._process_mode_doc(cfg_baseline, cfg_adapt, node_repo, document_id, req.language)
            elif req.mode == "window":
                self._process_mode_window(cfg_baseline, cfg_adapt, node_repo, document_id, req.source_lang, req.language, req.window_size)
            elif req.mode == "node":
                self._process_mode_node(cfg_baseline, cfg_adapt, node_repo, document_id, req.source_lang, req.language)
            else:
                raise HTTPException(status_code=400, detail=f"Modo não suportado: {req.mode}")

            # Recupera nós atualizados do banco (com as traduções recém-salvas)
            final_nodes = node_repo.list_nodes(document_id)
            results_html_dir = self.paths.results_dir / "html"
            results_html_dir.mkdir(parents=True, exist_ok=True)

            exporter = HTMLExportService()

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

        # ------------ Helpers por modo ------------
        def _get_retriever(cfg: PipelineConfig | None):
            if not cfg or not cfg.rag or not cfg.rag.enabled:
                return None
            from ...rag.retriever import Retriever
            index_dir = cfg.rag.index_dir or (cfg.paths.data_dir / "rag_index")
            r = Retriever(model_name=cfg.rag.model, index_dir=index_dir, db_path=cfg.paths.db_path)
            if not r.has_index():
                r.build_index()
            return r

        def _build_context(retriever, text: str, cfg: PipelineConfig) -> str | None:
            if not retriever:
                return None
            from ...rag.retriever import Retriever as _R
            q = text[: max(1000, len(text))]
            snippets = retriever.retrieve(q, top_k=cfg.rag.top_k, source_lang=cfg.source_lang, target_lang=cfg.target_langs[0])
            return _R.build_context(snippets, max_chars=cfg.rag.max_context_chars)

        def _save_baseline_and_adapted(node_repo: NodeRepository, nodes: list[dict], baseline_map: dict[int, str], adapted_map: dict[int, str] | None, context: str | None):
            for n in nodes:
                nid = n["id"]
                btxt = baseline_map.get(nid) or n.get("original_text", "")
                node_repo.save_baseline(node_id=nid, translation=btxt)
                atxt = adapted_map.get(nid) if adapted_map else btxt
                node_repo.save_adapted(node_id=nid, translation=atxt, context=context or "")

        def _list_nodes(node_repo: NodeRepository, document_id: int) -> list[dict]:
            return node_repo.list_nodes(document_id)

        def _process_doc(cfg_baseline: PipelineConfig, cfg_adapt: PipelineConfig | None, node_repo: NodeRepository, document_id: int, language: str):
            nodes_all = _list_nodes(node_repo, document_id)
            base = ServicoTraducao(cfg_baseline).traduzir_doc(nodes_all, target_lang=language)
            adapted = None
            context_used = None
            if cfg_adapt:
                adapted = ServicoTraducao(cfg_adapt).traduzir_doc(nodes_all, target_lang=language)
            _save_baseline_and_adapted(node_repo, nodes_all, base, adapted, context_used)

        def _process_window(cfg_baseline: PipelineConfig, cfg_adapt: PipelineConfig | None, node_repo: NodeRepository, document_id: int, source_lang: str, language: str, window_size: int = 3):
            nodes_all = _list_nodes(node_repo, document_id)
            ts_base = ServicoTraducao(cfg_baseline)
            ts_base.window_size = max(1, int(window_size))
            baseline_map = ts_base.traduzir_window(nodes_all, target_lang=language)
            adapted_map = None
            context_used = None
            if cfg_adapt:
                ts_adapt = ServicoTraducao(cfg_adapt)
                ts_adapt.window_size = ts_base.window_size
                # Para contexto por janela, podemos usar o mesmo texto da janela ou simplificar por nó; aqui reaproveitamos janela interna do serviço
                adapted_map = ts_adapt.traduzir_window(nodes_all, target_lang=language)
                # Contexto agregado não é trivial por janela; mantemos None ou poderíamos computar por janela separadamente
            _save_baseline_and_adapted(node_repo, nodes_all, baseline_map, adapted_map, context_used)

        def _process_node(cfg_baseline: PipelineConfig, cfg_adapt: PipelineConfig | None, node_repo: NodeRepository, document_id: int, source_lang: str, language: str):
            nodes_all = _list_nodes(node_repo, document_id)
            ts_base = ServicoTraducao(cfg_baseline)
            adapted_map = None
            context_used = None
            # Baseline nó a nó
            for n in nodes_all:
                btxt = ts_base.traduzir_node(n, target_lang=language)
                node_repo.save_baseline(node_id=n["id"], translation=btxt)
            if cfg_adapt:
                ts_adapt = ServicoTraducao(cfg_adapt)
                adapted_map = {}
                # Com RAG, poderíamos gerar contexto por nó
                retriever = _get_retriever(cfg_adapt)
                for n in nodes_all:
                    src = n.get("original_text", "")
                    contexto = _build_context(retriever, src, cfg_adapt) if src.strip() else None
                    atxt = ts_adapt._ensure_backend().translate(src, source_lang=source_lang, target_lang=language, contexto=contexto) if src.strip() else src
                    adapted_map[n["id"]] = atxt
                # Contexto global não se aplica; mantemos None
            _save_baseline_and_adapted(node_repo, nodes_all, {n["id"]: node_repo.get_node(n["id"]).get("baseline_text", "") for n in nodes_all}, adapted_map, context_used)

        # Bind helpers to instance for readability
        self._process_mode_doc = _process_doc
        self._process_mode_window = _process_window
        self._process_mode_node = _process_node
