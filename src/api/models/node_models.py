from __future__ import annotations

from pydantic import BaseModel


class HumanTextUpdate(BaseModel):
    texto: str
    overwrite_adapted: bool = False
