from __future__ import annotations

from fastapi import HTTPException
from ..controllers.base_controller import BaseController
from ...persistence.db import Database
from ...persistence.rag_repos import GlossaryRepository, GlossaryDuplicateError
from ...core.config import PathsConfig
from ..models.glossary_models import GlossaryCreate, GlossaryUpdate

class GlossaryController(BaseController):
    def __init__(self, paths: PathsConfig):
        # Endpoints em português e tag amigável para documentação
        super().__init__(prefix="/glossario", tags=["glossario"])
        self.db = Database(paths.db_path)
        self.repo = GlossaryRepository(self.db)
        r = self.router

        @r.get(
            "/entradas",
            summary="Listar entradas do glossário",
            description=(
                "Retorna as entradas do glossário. Você pode filtrar por língua de origem (lang_src) "
                "e/ou língua de destino (lang_tgt)."
            ),
        )
        def listar_entradas(lang_src: str | None = None, lang_tgt: str | None = None):
            return self.repo.list_entries(lang_src=lang_src, lang_tgt=lang_tgt)

        @r.post(
            "/entradas",
            summary="Criar entrada no glossário",
            description="Adiciona um novo termo ao glossário com idiomas de origem e destino e notas opcionais.",
        )
        def criar_entrada(payload: GlossaryCreate):
            try:
                entry_id = self.repo.add_entry(
                    term_src=payload.term_src,
                    lang_src=payload.lang_src,
                    term_tgt=payload.term_tgt,
                    lang_tgt=payload.lang_tgt,
                    notes=payload.notes,
                )
            except GlossaryDuplicateError:
                raise HTTPException(
                    status_code=409,
                    detail="Termo já cadastrado para essa combinação de idiomas.",
                )
            return {"id": entry_id}

        @r.put(
            "/entradas/{entrada_id}",
            summary="Atualizar entrada do glossário",
            description="Atualiza os campos de uma entrada existente do glossário pelo seu ID.",
        )
        def atualizar_entrada(entrada_id: int, payload: GlossaryUpdate):
            try:
                ok = self.repo.update_entry(
                    entrada_id,
                    term_src=payload.term_src,
                    lang_src=payload.lang_src,
                    term_tgt=payload.term_tgt,
                    lang_tgt=payload.lang_tgt,
                    notes=payload.notes,
                )
            except GlossaryDuplicateError:
                raise HTTPException(
                    status_code=409,
                    detail="Termo já cadastrado para essa combinação de idiomas.",
                )
            if not ok:
                raise HTTPException(status_code=404, detail="entry not updated or not found")
            return {"updated": True}

        @r.delete(
            "/entradas/{entrada_id}",
            summary="Excluir entrada do glossário",
            description="Remove uma entrada do glossário dado o seu ID.",
        )
        def excluir_entrada(entrada_id: int):
            ok = self.repo.delete_entry(entrada_id)
            if not ok:
                raise HTTPException(status_code=404, detail="entry not found")
            return {"deleted": True}
