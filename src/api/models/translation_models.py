from __future__ import annotations
from pydantic import BaseModel

class QuickTranslateRequest(BaseModel):
    document: str
    target_lang: str = "en"
    backend: str = "hf"  # hf|google
    rag_topk: int = 3
