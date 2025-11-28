from __future__ import annotations
from pydantic import BaseModel

class ProcessRequest(BaseModel):
    input: str
    language: str = "en"
    source_lang: str = "pt"
    backend: str = "google"  # hf|google
    mode: str = "doc"  # node|window|doc
    rag_topk: int = 0  # >0 ativa tradução adaptada adicional com RAG
