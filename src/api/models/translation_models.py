from __future__ import annotations
from pydantic import BaseModel

class QuickTranslateRequest(BaseModel):
    document: str
    target_lang: str = "en"
    rag_topk: int = 3
