from __future__ import annotations

import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env (se existir)
load_dotenv()

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.config import PathsConfig
from .controllers.glossary_controller import GlossaryController
from .controllers.corpus_controller import CorpusController
from .controllers.translation_controller import TranslationController
from .controllers.process_controller import ProcessController
from .controllers.feedback_controller import FeedbackController
from .controllers.export_controller import ExportController
from .controllers.evaluation_controller import EvaluationController

app = FastAPI(title="NLP TCC API", version="0.2")

# Configuração CORS simplificada para desenvolvimento local
# Permite qualquer origem, método e header para evitar bloqueios durante testes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instancia routers de controllers separados (camada de apresentação)
paths_for_controllers = None
def get_paths() -> PathsConfig:
    global paths_for_controllers
    if paths_for_controllers is None:
        project_root = Path(__file__).resolve().parents[2]
        paths_for_controllers = PathsConfig(
            project_root=project_root,
            data_dir=project_root / "data",
            db_path=project_root / "data" / "db" / "nlp_tcc.sqlite",
            glossario_dir=project_root / "glossario",
            corpus_dir=project_root / "corpus",
            results_dir=project_root / "results",
        )
    return paths_for_controllers

paths_obj = get_paths()
app.include_router(GlossaryController(paths_obj).get_router())
app.include_router(CorpusController(paths_obj).get_router())
app.include_router(TranslationController(paths_obj).get_router())
app.include_router(ProcessController(paths_obj).get_router())
app.include_router(FeedbackController(paths_obj).get_router())
app.include_router(ExportController(paths_obj).get_router())
app.include_router(EvaluationController(paths_obj).get_router())


def build_paths() -> PathsConfig:
    return get_paths()


@app.get("/health")
def health():
    return {"status": "ok"}


# Redireciona a raiz para a documentação Swagger UI
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
