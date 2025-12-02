from __future__ import annotations

from fastapi import APIRouter

class BaseController:
    """Base para controllers. Cada controller possui um APIRouter.
    Pode estender para adicionar utilidades comuns (auth, logging, etc.).
    """
    def __init__(self, prefix: str, tags: list[str]):
        self.router = APIRouter(prefix=prefix, tags=tags)

    def get_router(self) -> APIRouter:
        return self.router
