from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .base_controller import BaseController
from ...core.config import PathsConfig
from ...persistence.db import Database
from ...persistence.repos import DocumentRepository, NodeRepository
from ...services.export_service import ExportService
from ...services.text_export_service import TextExportService
from ..models.export_models import ExportRequest
from ...html_io import read_html

class ExportController(BaseController):
    def __init__(self, paths: PathsConfig):
        # Endpoints de exportação em português
        super().__init__(prefix="/exportar", tags=["exportacao"])
        self.paths = paths
        self.db = Database(paths.db_path)
        self.doc_repo = DocumentRepository(self.db)
        self.node_repo = NodeRepository(self.db)
        r = self.router

        @r.post(
            "/html",
            summary="Exportar HTML traduzido",
            description=(
                "Gera um HTML de saída com a variante selecionada (baseline/adapted) para o documento "
                "e idioma informados."
            ),
        )
        def exportar_html(req: ExportRequest):
            document_id = self.doc_repo.find_document_id(req.doc, req.source_lang, req.language)
            if not document_id:
                raise HTTPException(status_code=404, detail="document not found")
            nodes = self.node_repo.list_nodes(document_id)
            html_path = self.paths.data_dir / "extracted" / f"{req.doc}_indexed.html"
            original_html = read_html(html_path)
            out = self.paths.results_dir / "html" / f"{req.doc}_{req.variant}_{req.language}.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            ExportService().export_variant(original_html, nodes, req.variant, out)
            return {"output": str(out)}

        @r.post(
            "/texto",
            summary="Exportar texto traduzido",
            description="Exporta a variante escolhida como um arquivo .txt com o conteúdo linearizado.",
        )
        def exportar_texto(req: ExportRequest):
            document_id = self.doc_repo.find_document_id(req.doc, req.source_lang, req.language)
            if not document_id:
                raise HTTPException(status_code=404, detail="document not found")
            nodes = self.node_repo.list_nodes(document_id)
            html_path = self.paths.data_dir / "extracted" / f"{req.doc}_indexed.html"
            original_html = read_html(html_path)
            out = self.paths.results_dir / "text" / f"{req.doc}_{req.variant}_{req.language}.txt"
            out.parent.mkdir(parents=True, exist_ok=True)
            TextExportService().export_variant_text(original_html, nodes, req.variant, out)
            return {"output": str(out)}
