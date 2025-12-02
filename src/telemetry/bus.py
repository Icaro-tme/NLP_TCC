"""Simple synchronous event bus for translation telemetry."""

from __future__ import annotations

from typing import Callable, List

from .events import TranslationEvent

EventHandler = Callable[[TranslationEvent], None]


class TranslationEventBus:
    def __init__(self) -> None:
        self._handlers: List[EventHandler] = []

    def register(self, handler: EventHandler) -> None:
        if handler in self._handlers:
            return
        self._handlers.append(handler)

    def unregister(self, handler: EventHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    def emit(self, event: TranslationEvent) -> None:
        for handler in list(self._handlers):
            try:
                handler(event)
            except Exception:
                # Observers are optional; swallow errors to avoid breaking pipeline.
                continue

    def clear(self) -> None:
        self._handlers.clear()


event_bus = TranslationEventBus()


def emit_event(event: TranslationEvent) -> None:
    if not event_bus._handlers:
        return
    event_bus.emit(event)
