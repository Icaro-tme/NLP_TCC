from __future__ import annotations
from pydantic import BaseModel
from typing import List, Optional

class GlossaryFeedbackRequest(BaseModel):
    source: str
    target: str
    source_lang: str = "pt"
    target_lang: str = "en"
    notes: str | None = None

class CorpusFeedbackRequest(BaseModel):
    text: str
    language: str = "pt"
    tags: List[str] | None = None
    notes: str | None = None

class HumanTranslationRequest(BaseModel):
    translation: str
    overwrite_adapted: bool = False
    context: str | None = None
