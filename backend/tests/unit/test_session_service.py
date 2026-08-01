"""Unit tests: SessionService (create, validate, rotate, revoke)."""

from __future__ import annotations

import uuid

import pytest

from app.application.services.session_service import SessionService
from app.core.config import Settings
from app.domain.models.enums import SessionStatus
from app.domain.models.identity import Session, User
from app.infrastructure.db.session import Database
from tests.conftest import FakeRedis


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
        SESSION_TTL_SECONDS=3600,
        SESSION_IDLE_TIMEOUT_SECONDS=600,
    )


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.mark.asyncio
async def test_create_validate_rotate_revoke(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = SessionService(session, fake_redis, _settings())
        user = User(email="s@example.com", password_hash="h")
        session.add(user)
        await session.flush()

        raw, db_sess = await svc.create_session(
            user_id=user.id,
            user_agent="pytest/1.0",
            ip_address="127.0.0.1",
            remember_me=False,
            device_label="unit",
        )
        assert raw
        assert db_sess.status == SessionStatus.ACTIVE

        record = await svc.validate(raw)
        assert record is not None
        assert record.user_id == str(user.id)
        assert record.device_label == "unit"

        # Invalid token → None.
        assert await svc.validate("bogus") is None

        # list_active + count_active + has_active_sessions
        active = await svc.list_active(user.id, current_session_id=db_sess.id)
        assert len(active) == 1
        assert active[0].is_current is True
        assert await svc.count_active(user.id) is True
        assert await svc.has_active_sessions(user.id) is True

        # Rotate.
        new_token = await svc.rotate(raw)
        assert new_token is not None
        assert await svc.validate(raw) is None  # old token gone
        assert await svc.validate(new_token) is not None

        # touch() updates last_used.
        await svc.touch(new_token)
        assert await svc.validate(new_token) is not None

        # revoke_by_token.
        await svc.revoke_by_token(new_token)
        assert await svc.validate(new_token) is None
    await db.dispose()


@pytest.mark.asyncio
async def test_validate_expired_absolute(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = SessionService(session, fake_redis, _settings())
        user = User(email="e@example.com", password_hash="h")
        session.add(user)
        await session.flush()

        raw, db_sess = await svc.create_session(user_id=user.id, user_agent=None, ip_address=None)
        # Force absolute expiry into the past.
        record = await fake_redis.get(f"gp:session:{svc._hash(raw)}")
        import json

        payload = json.loads(record)
        payload["absolute_expiry"] = 1
        payload["idle_expiry"] = 1
        await fake_redis.set(f"gp:session:{svc._hash(raw)}", json.dumps(payload))

        assert await svc.validate(raw) is None
        # DB session marked expired.
        db_sess = await session.get(Session, db_sess.id)
        assert db_sess.status == SessionStatus.EXPIRED
    await db.dispose()


@pytest.mark.asyncio
async def test_rotate_missing_token(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = SessionService(session, fake_redis, _settings())
        assert await svc.rotate("nope") is None
    await db.dispose()


@pytest.mark.asyncio
async def test_revoke_all_for_user(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = SessionService(session, fake_redis, _settings())
        user = User(email="a@example.com", password_hash="h")
        session.add(user)
        await session.flush()

        tok1, _ = await svc.create_session(user_id=user.id, user_agent=None, ip_address=None)
        tok2, _ = await svc.create_session(user_id=user.id, user_agent=None, ip_address=None)

        n = await svc.revoke_all_for_user(user.id, except_token=tok1)
        assert n == 1
        assert await svc.validate(tok1) is not None
        assert await svc.validate(tok2) is None

        # revoke by db id → DB status becomes revoked.
        record = await svc.validate(tok1)
        await svc.revoke(uuid.UUID(record.session_db_id), user.id, reason="admin")
        db_sess = await session.get(Session, uuid.UUID(record.session_db_id))
        assert db_sess.status == SessionStatus.REVOKED
        assert db_sess.revoked_reason == "admin"
    await db.dispose()


@pytest.mark.asyncio
async def test_revoke_by_token_missing(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = SessionService(session, fake_redis, _settings())
        await svc.revoke_by_token("missing")  # no-op, no raise
    await db.dispose()


def test_safe_ip_handles_invalid_and_ipv6():
    assert SessionService._safe_ip("not-an-ip") == "not-an-ip"[:45]
    assert SessionService._safe_ip("2001:db8::1") == "2001:db8::1"
    assert SessionService._safe_ip("8.8.8.8") == "8.8.8.8"
