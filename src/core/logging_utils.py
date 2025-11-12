from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator


def get_logger(name: str = "nlp_tcc") -> logging.Logger:
    """Return a logger configured with a sensible default handler."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


@contextmanager
def log_time(logger: logging.Logger, action: str) -> Iterator[None]:
    """Context manager that logs start/end of an action with duration."""
    import time

    start = time.perf_counter()
    logger.info("start %s", action)
    try:
        yield
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        logger.info("end %s (%.2f ms)", action, elapsed)
