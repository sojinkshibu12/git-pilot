"""Unit tests: generic DB repositories (in-memory SQLite)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.core.config import Settings
from app.domain.models.identity import User
from app.infrastructure.db.repositories import Repository, UsersRepository
from app.infrastructure.db.session import Database


def _settings() -> Settings:
    return Settings(
        APP_ENV="testing",
        SECRET_KEY="k" * 32,
        TOKEN_ENCRYPTION_KEY="d" * 64,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://fake",
        GITHUB_CLIENT_ID="cid",
        GITHUB_CLIENT_SECRET="csec",
        GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
    )


def _user(email: str, **kw) -> User:
    return User(email=email, password_hash="hash", **kw)


@pytest.mark.asyncio
async def test_repository_crud_and_soft_delete():
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        repo = Repository(session, User)
        u = await repo.add(_user("a@example.com"))
        assert u.id is not None

        got = await repo.get(u.id)
        assert got is not None
        assert got.id == u.id

        missing = await repo.get(uuid.uuid4())
        assert missing is None

        await repo.soft_delete(u)
        # Soft-deleted rows excluded by default.
        assert await repo.get(u.id) is None
        # ...but included when requested.
        assert await repo.get(u.id, include_deleted=True) is not None

        await repo.delete(u)
        assert await repo.get(u.id, include_deleted=True) is None
    await db.dispose()


@pytest.mark.asyncio
async def test_users_repository_add():
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        users = UsersRepository(session, User)
        u = await users.add(_user("b@example.com"))
        assert u.email == "b@example.com"
        assert u.created_at is not None
        assert u.created_at.tzinfo is not None or isinstance(u.created_at, datetime)
    await db.dispose()
