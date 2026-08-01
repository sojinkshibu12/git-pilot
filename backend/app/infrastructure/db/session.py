"""Async SQLAlchemy engine + scoped session management.

A single `Database` container (engine + sessionmaker) is created at application
startup and exposed on `app.state.db`. Requests obtain a session via the
`get_db_session` dependency.

- Connection pooling tuned for many concurrent requests.
- Atomic session-per-request lifecycle (rollback on error).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.models.base import Base

logger = get_logger("db")


class Database:
    """Owns the engine + sessionmaker for one process."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine
        self.session_factory: async_sessionmaker[AsyncSession]

        engine_kwargs: dict = {
            "echo": settings.DB_ECHO,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
        if settings.is_testing:
            if settings.DATABASE_URL.startswith("sqlite") and ":memory:" in settings.DATABASE_URL:
                # A single shared in-memory connection so tests can create tables
                # on one connection and query them from every session.
                engine_kwargs = {
                    "echo": False,
                    "poolclass": StaticPool,
                    "connect_args": {"check_same_thread": False},
                }
            else:
                engine_kwargs = {"echo": False, "poolclass": NullPool}

        self.engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

        if settings.DATABASE_URL.startswith("sqlite"):
            @event.listens_for(self.engine.sync_engine, "connect")
            def _sqlite_compat(dbapi_connection: object, connection_record: object) -> None:  # noqa: ARG001
                cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
                # SQLite has no builtin `now()`; models use `now()` server defaults
                # (Postgres) — register a compatible function for tests.
                try:
                    dbapi_connection.create_function(  # type: ignore[attr-defined]
                        "now", 0, lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                    )
                except Exception:  # noqa: BLE001 - non-sqlite3 drivers may not support it
                    pass

        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def init_db(self) -> None:
        """Create tables directly. Only intended for tests / ephemeral environments."""
        if self.settings.is_testing:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session from app.state.db."""
    db: Database | None = getattr(request.app.state, "db", None)
    if db is None:
        raise RuntimeError("Database not initialised — call lifespan bootstrap first.")
    async with db.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
