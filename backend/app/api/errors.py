"""Global exception handlers → stable, documented error responses.

Maps domain exceptions to HTTP responses with machine-readable codes. Never
leaks stack traces, SQL, or token material.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    DomainError,
    GitHubRateLimitedError,
    RateLimitExceeded,
)
from app.core.logging import get_logger

logger = get_logger("http")


def _ctx(request: Request) -> dict[str, object]:
    return {
        "request_id": getattr(request.state, "request_id", None),
        "correlation_id": getattr(request.state, "correlation_id", None),
        "path": request.url.path,
        "method": request.method,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        payload = {
            "detail": exc.message,
            "code": exc.code,
            "status": exc.status_code,
        }
        if exc.details:
            payload["data"] = exc.details
        if isinstance(exc, RateLimitExceeded):
            payload["retry_after_seconds"] = exc.details.get("retry_after_seconds")
        if isinstance(exc, GitHubRateLimitedError):
            payload["retry_after_seconds"] = exc.details.get("reset_at")
        log = logger.bind(**_ctx(request))
        if exc.status_code >= 500 or exc.code in {
            "oauth_state_mismatch",
            "pkce_validation_failed",
            "redirect_uri_mismatch",
        }:
            log.warning("domain_error", code=exc.code, status=exc.status_code, detail=exc.message)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = ".".join(
                str(x) for x in err.get("loc", []) if x not in {"body", "query", "path", "header"}
            )
            fields.setdefault(loc, []).append(err.get("msg", "invalid value"))
        logger.warning("validation_error", **_ctx(request), errors=exc.errors()[:5])
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation failed.",
                "code": "validation_failed",
                "status": 422,
                "fields": fields,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            429: "rate_limit_exceeded",
            500: "internal_error",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": str(exc.detail),
                "code": code_map.get(exc.status_code, "http_error"),
                "status": exc.status_code,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", **_ctx(request), error=str(exc))
        from app.core.config import get_settings

        detail = "An unexpected error occurred."
        if str(get_settings().APP_ENV) != "production":
            detail = f"{type(exc).__name__}: {exc}"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "code": "internal_error", "status": 500},
        )
