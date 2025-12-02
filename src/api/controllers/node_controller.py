from __future__ import annotations

from fastapi import HTTPException

from .base_controller import BaseController
from ...core.config import PathsConfig
from ...persistence.db import Database
from ...persistence.repos import NodeRepository, DocumentRepository
from ..models.node_models import HumanTextUpdate


class NodeController(BaseController):
    """Endpoints para inspeção e atualização de traduções humanas por nó.

    Permite recuperar dados completos de um nó e salvar `human_text` preservando
    opcionalmente a variante adapted.
    """

    def __init__(self, paths: PathsConfig):
        super().__init__(prefix="/nodos", tags=["nodos"])
        self.paths = paths
        self.db = Database(paths.db_path)
        self.node_repo = NodeRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)
        r = self.router

        @r.get("/{node_id}", summary="Obter dados de um nó")
        def obter_no(node_id: int):
            node = self.node_repo.get_node(node_id)
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            return {
                "id": node["id"],
                "document_id": node.get("document_id"),
                "node_path": node.get("node_path"),
                "tag": node.get("tag"),
                "original_text": node.get("original_text"),
                "baseline_text": node.get("baseline_text"),
                "adapted_text": node.get("adapted_text"),
                "human_text": node.get("human_text"),
                "context_text": node.get("context_text"),
                "status_adapted": node.get("status_adapted"),
                "status_human": node.get("status_human"),
            }

        @r.post("/{node_id}/humano", summary="Salvar texto humano para o nó")
        def salvar_humano(node_id: int, payload: HumanTextUpdate):
            node = self.node_repo.get_node(node_id)
            if not node:
                raise HTTPException(status_code=404, detail="node not found")
            self.node_repo.save_human_translation(
                node_id=node_id,
                translation=payload.texto,
                overwrite_adapted=payload.overwrite_adapted,
            )
            atualizado = self.node_repo.get_node(node_id)
            return {
                "id": atualizado["id"],
                "human_text": atualizado.get("human_text"),
                "adapted_text": atualizado.get("adapted_text"),
                "baseline_text": atualizado.get("baseline_text"),
                "status_human": atualizado.get("status_human"),
            }
