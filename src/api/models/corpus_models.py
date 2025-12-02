from __future__ import annotations
from pydantic import BaseModel
from typing import List

class CorpusCreate(BaseModel):
    text: str
    language: str = "pt"
    tags: List[str] | None = None
    notes: str | None = None

class CorpusUpdate(BaseModel):
    text: str | None = None
    language: str | None = None
    tags: List[str] | None = None
    notes: str | None = None
