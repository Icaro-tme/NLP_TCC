from __future__ import annotations
from pydantic import BaseModel

class ExportRequest(BaseModel):
    doc: str
    language: str
    variant: str = "adapted"
    source_lang: str = "pt"
