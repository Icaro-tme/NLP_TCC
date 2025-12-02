from __future__ import annotations

from fastapi import HTTPException

from .base_controller import BaseController
from ...core.config import PathsConfig
from ...persistence.db import Database
from ...persistence.rag_repos import GlossaryRepository, CorpusRepository
from ..models.feedback_models import GlossaryFeedbackRequest, CorpusFeedbackRequest, HumanTranslationRequest
from ...persistence.repos import NodeRepository
from ...rag.utils import invalidate_rag_index

class FeedbackController(BaseController):
    def __init__(self, paths: PathsConfig):
        # Mantém rotas no nível raiz com caminhos em português
        super().__init__(prefix="", tags=["feedback"])  # root-level paths for clarity
        self.paths = paths
        self.db = Database(paths.db_path)
        self.gloss_repo = GlossaryRepository(self.db)
        self.corpus_repo = CorpusRepository(self.db)
        r = self.router

        @r.post(
            "/feedback/glossario",
            summary="Feedback de glossário",
            description=(
                "Cadastra um par termo origem/destino no glossário a partir de feedback humano e "
                "invalida o índice RAG para reconstrução posterior."
            ),
        )
        def feedback_glossario(req: GlossaryFeedbackRequest):
            self.gloss_repo.add_entry(
                term_src=req.source,
                lang_src=req.source_lang,
                term_tgt=req.target,
                lang_tgt=req.target_lang,
                notes=req.notes,
            )
            invalidate_rag_index(self.paths)
            return {"status": "recorded"}

        @r.post(
            "/feedback/corpus",
            summary="Feedback de corpus",
            description="Adiciona um novo trecho de texto ao corpus a partir de feedback humano.",
        )
        def feedback_corpus(req: CorpusFeedbackRequest):
            if not req.text.strip():
                raise HTTPException(status_code=400, detail="campo 'text' não pode estar vazio")
            self.corpus_repo.add_snippet(
                text=req.text,
                language=req.language,
                tags=req.tags or [],
                notes=req.notes,
            )
            invalidate_rag_index(self.paths)
            return {"status": "recorded"}

        @r.post(
            "/nos/{no_id}/traducao-humana",
            summary="Registrar tradução humana para um nó",
            description=(
                "Salva a tradução humana de um nó específico. Opcionalmente pode sobrescrever a tradução "
                "adaptada e registrar contexto."
            ),
        )
        def definir_traducao_humana(no_id: int, req: HumanTranslationRequest):
            node_repo = NodeRepository(self.db)
            node = node_repo.get_node(no_id)
            if not node:
                raise HTTPException(status_code=404, detail="nó não encontrado")
            node_repo.save_human_translation(
                node_id=no_id,
                translation=req.translation,
                overwrite_adapted=req.overwrite_adapted,
                context=req.context,
            )
            return {"no_id": no_id, "status": "updated"}
