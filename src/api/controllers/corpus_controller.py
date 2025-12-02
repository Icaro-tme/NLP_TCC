from __future__ import annotations

from fastapi import HTTPException
from ..controllers.base_controller import BaseController
from ...persistence.db import Database
from ...persistence.rag_repos import CorpusRepository
from ...core.config import PathsConfig
from ..models.corpus_models import CorpusCreate, CorpusUpdate

class CorpusController(BaseController):
    def __init__(self, paths: PathsConfig):
        # Mantemos "/corpus" como prefixo e traduzimos os recursos
        super().__init__(prefix="/corpus", tags=["corpus"])
        self.db = Database(paths.db_path)
        self.repo = CorpusRepository(self.db)
        r = self.router

        @r.get(
            "/trechos",
            summary="Listar trechos do corpus",
            description=(
                "Retorna trechos do corpus, opcionalmente filtrando por línguas via parâmetro 'languages' "
                "(lista separada por vírgula)."
            ),
        )
        def listar_trechos(languages: str | None = None):
            langs = [l.strip() for l in languages.split(",") if l.strip()] if languages else None
            return self.repo.list_snippets(languages=langs)

        @r.post(
            "/trechos",
            summary="Criar trecho de corpus",
            description="Adiciona um novo trecho ao corpus com idioma, tags e notas opcionais.",
        )
        def criar_trecho(payload: CorpusCreate):
            sid = self.repo.add_snippet(
                text=payload.text,
                language=payload.language,
                tags=payload.tags,
                notes=payload.notes,
            )
            return {"id": sid}

        @r.put(
            "/trechos/{trecho_id}",
            summary="Atualizar trecho do corpus",
            description="Atualiza os campos de um trecho existente do corpus pelo seu ID.",
        )
        def atualizar_trecho(trecho_id: int, payload: CorpusUpdate):
            ok = self.repo.update_snippet(
                trecho_id,
                text=payload.text,
                language=payload.language,
                tags=payload.tags,
                notes=payload.notes,
            )
            if not ok:
                raise HTTPException(status_code=404, detail="snippet not updated or not found")
            return {"updated": True}

        @r.delete(
            "/trechos/{trecho_id}",
            summary="Excluir trecho do corpus",
            description="Remove um trecho do corpus dado o seu ID.",
        )
        def excluir_trecho(trecho_id: int):
            ok = self.repo.delete_snippet(trecho_id)
            if not ok:
                raise HTTPException(status_code=404, detail="snippet not found")
            return {"deleted": True}
