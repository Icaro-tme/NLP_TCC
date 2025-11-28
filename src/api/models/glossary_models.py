from __future__ import annotations
from pydantic import BaseModel

class GlossaryCreate(BaseModel):
    term_src: str
    lang_src: str = "pt"
    term_tgt: str
    lang_tgt: str = "en"
    notes: str | None = None

class GlossaryUpdate(BaseModel):
    term_src: str | None = None
    lang_src: str | None = None
    term_tgt: str | None = None
    lang_tgt: str | None = None
    notes: str | None = None
