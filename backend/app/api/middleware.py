"""HTTP middleware: request IDs, correlation, security headers, session cookie rotation.

Order (outer → inner) is configured in `make_app`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.api.cookies import set_session_cookie
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("middleware")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request_id + correlation_id to every request (including errors)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.correlation_id = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request.state.request_id,
            correlation_id=request.state.correlation_id,
        )
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """OWASP-recommended security headers on all responses."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; connect-src 'self'; object-src 'none'",
        )
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if self._settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={self._settings.HSTS_MAX_AGE}; includeSubDomains",
            )
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        return response


class SessionCookieRotationMiddleware(BaseHTTPMiddleware):
    """Apply pending session-token rotation set by auth dependencies."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        new_token = getattr(request.state, "new_session_token", None)
        if new_token:
            set_session_cookie(response, new_token, self._settings)
        return response


class CSRFCheckMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin mutating requests lacking a valid origin/referer.

    Defense-in-depth alongside the X-CSRF-Token double-submit guard.
    """

    _SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

    def __init__(self, app: ASGIApp, settings: Settings, cors_origins: list[str]) -> None:
        super().__init__(app)
        self._settings = settings
        self._origins = set(cors_origins)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in self._SAFE_METHODS:
            return await call_next(request)
        if request.url.path.startswith(self._settings.API_V1_PREFIX + "/oauth"):
            return await call_next(request)
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        base_url = f"{request.base_url.scheme}://{request.base_url.hostname or ''}"
        if origin:
            if origin not in self._origins and not origin.startswith(base_url):
                logger.warning("csrf_origin_rejected", origin=origin, path=request.url.path)
                return Response(
                    status_code=403,
                    content='{"detail":"Origin rejected","code":"csrf_origin","status":403}',
                )
        elif referer:
            from urllib.parse import urlparse

            host = urlparse(referer).hostname
            if host and host not in {request.base_url.hostname} | {
                urlparse(o).hostname for o in self._origins
            }:
                logger.warning("csrf_referer_rejected", referer=referer, path=request.url.path)
                return Response(
                    status_code=403,
                    content='{"detail":"Referer rejected","code":"csrf_referer","status":403}',
                )
        return await call_next(request)


class SecurityLogMiddleware(BaseHTTPMiddleware):
    """Request logging with timing and status."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        import time

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            ip=request.client.host if request.client else None,
            ua=request.headers.get("user-agent"),
        )
        return response
