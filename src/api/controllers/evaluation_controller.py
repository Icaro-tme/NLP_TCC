from __future__ import annotations

from fastapi import UploadFile, File, Form, HTTPException
from fastapi import status
from fastapi.responses import JSONResponse

from .base_controller import BaseController
from ...core.config import PathsConfig
from ...services.evaluation_service import EvaluationService


class EvaluationController(BaseController):
    def __init__(self, paths: PathsConfig):
        super().__init__(prefix="/avaliar", tags=["avaliacao"])
        self.paths = paths
        self.service = EvaluationService(paths)
        r = self.router

        @r.post(
            "",
            summary="Avaliar qualidade de tradução",
            description=(
                "Recebe um HTML com tradução humana (baseado em variante exportada) e compara com a variante do sistema usando métricas BLEU, chrF, TER, Jaccard e similaridade sintática (POS)."
            ),
        )
        async def avaliar(
            documento: str = Form(...),
            source_lang: str = Form("pt"),
            idioma: str = Form("en"),
            variante: str = Form("adapted"),
            arquivo: UploadFile = File(...),
        ):
            if variante not in ("baseline", "adapted"):
                raise HTTPException(status_code=400, detail="Variante inválida (use baseline ou adapted).")
            try:
                content_bytes = await arquivo.read()
                human_html = content_bytes.decode("utf-8", errors="ignore")
                resultado = self.service.compute_doc(
                    documento=documento,
                    source_lang=source_lang,
                    target_lang=idioma,
                    variante=variante,
                    human_html=human_html,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Erro na avaliação: {e}")
            payload = {
                "documento": resultado.documento,
                "idioma": resultado.idioma,
                "variante": resultado.variante,
                "bleu": resultado.bleu,
                "chrf": resultado.chrf,
                "ter": resultado.ter,
                "jaccard_medio": resultado.jaccard_medio,
                "pos_accuracy_media": resultado.pos_accuracy_media,
                "sintaxe_habilitada": resultado.sintaxe_habilitada,
            }
            payload.update({
                "texto_humano": getattr(resultado, "texto_humano", None),
                "texto_sistema": getattr(resultado, "texto_sistema", None),
            })
            return JSONResponse(status_code=status.HTTP_200_OK, content=payload)
