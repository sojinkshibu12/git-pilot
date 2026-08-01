"""GitPilot API — application factory.

Startup bootstraps infrastructure (DB, Redis, vault, GitHub client) and exposes
them on `app.state` for the per-request dependency graph.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import (
    CSRFCheckMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    SecurityLogMiddleware,
    SessionCookieRotationMiddleware,
)
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging
from app.core.security import TokenVault, configure_vault
from app.infrastructure.db.session import Database
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.redis.client import RedisClient

logger = get_logger("app")


def make_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Infrastructure bootstrapping.
        db = Database(settings)
        await db.init_db()
        redis = RedisClient(settings)
        vault = configure_vault(settings)
        github = GitHubAPIClient(settings, redis)

        app.state.db = db
        app.state.redis = redis
        app.state.vault = vault
        app.state.github = github
        app.state.version = settings.APP_VERSION
        app.state.settings = settings

        logger.info("startup_complete", env=settings.APP_ENV.value, version=settings.APP_VERSION)
        try:
            yield
        finally:
            await github.aclose()
            await redis.close()
            await db.dispose()
            logger.info("shutdown_complete")

    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    )
    # Order matters: outermost last.
    app.add_middleware(SecurityLogMiddleware)
    app.add_middleware(CSRFCheckMiddleware, settings=settings, cors_origins=settings.CORS_ORIGINS)
    app.add_middleware(SessionCookieRotationMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    register_exception_handlers(app)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"service": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}

    return app


app = make_app()
