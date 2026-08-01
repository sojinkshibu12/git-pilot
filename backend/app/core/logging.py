"""Structured, correlation-aware logging built on structlog.

Every log line carries: timestamp, level, event, environment, request id,
correlation id, and (when available) user / session context.
"""
from __future__ import annotations

import logging
import sys
import time
from typing import Any

import structlog
from pythonjsonlogger.json import JsonFormatter

from app.core.config import Environment, get_settings

_CONFIG = get_settings()


def _get_renderer() -> Any:
    if _CONFIG.APP_ENV in {Environment.LOCAL, Environment.TESTING}:
        return structlog.dev.ConsoleRenderer(colors=True, sort_keys=False)
    return structlog.processors.JSONRenderer(serializer=_json_serializer)


def _json_serializer(data: dict) -> str:
    import json

    return json.dumps(data, default=str, separators=(",", ":"))


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger + structlog pipeline."""
    log_level = (level or ("DEBUG" if _CONFIG.DEBUG else "INFO")).upper()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            _get_renderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route standard-library logging through structlog too.
    logging.basicConfig(level=log_level)
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if _CONFIG.APP_ENV in {Environment.STAGING, Environment.PRODUCTION}:
        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"levelname": "level", "asctime": "ts", "name": "logger"},
        )
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)

    for noisy in ("uvicorn.access", "httpx", "httpcore", "asyncpg"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


class Timer:
    """Context manager for measuring operation durations."""

    def __init__(self, label: str, logger: structlog.stdlib.BoundLogger) -> None:
        self._label = label
        self._logger = logger
        self._started: float | None = None

    def __enter__(self) -> "Timer":
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        assert self._started is not None
        self._logger.debug("timed_operation", operation=self._label, duration_ms=round(
            (time.perf_counter() - self._started) * 1000, 2
        ))
