"""Unit tests: AuthService (register, login, verification, unlink)."""

from __future__ import annotations

import uuid

import pytest

from app.application.services.audit_service import AuditService
from app.application.services.auth_service import AuthService
from app.application.services.oauth_service import OAuthService
from app.application.services.session_service import SessionService
from app.application.services.token_service import TokenService
from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError, ValidationFailure
from app.core.security import TokenVault, verify_password
from app.domain.models.identity import GitHubAccount, User
from app.infrastructure.db.session import Database
from tests.conftest import FakeGitHubClient, FakeRedis

STRONG = "Str0ng-Passw0rd!-2026"


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
        EMAIL_VERIFICATION_TOKEN_TTL=3600,
    )


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.mark.asyncio
async def test_register_and_verify_email(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, settings, audit)
        tokens = TokenService(session, TokenVault("d" * 64))
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=audit,
            github=github,
            redis=fake_redis,
        )
        svc = AuthService(
            settings=settings,
            db=session,
            redis=fake_redis,
            audit=audit,
            sessions=sessions,
            oauth=oauth,
            tokens=tokens,
        )

        user = await svc.register(
            email="Alice@Example.com",
            password=STRONG,
            display_name="Alice",
            ip_address="127.0.0.1",
            user_agent="pytest",
            request_id="req-1",
        )
        assert user.email == "alice@example.com"
        assert user.status == "pending_email"

        # Duplicate register → conflict.
        with pytest.raises(ConflictError):
            await svc.register(
                email="alice@example.com",
                password=STRONG,
                display_name=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )

        # Request + verify email.
        token = await svc.request_email_verification(user_id=user.id)
        assert await svc.verify_email(token=token) is True
        user = await session.get(User, user.id)
        assert user.email_verified is True
        assert user.status == "active"

        # Verify with a wrong user_id → False.
        token2 = await svc.request_email_verification(user_id=user.id)
        assert await svc.verify_email(token=token2, user_id=uuid.uuid4()) is False

        # Verify garbage token → False.
        assert await svc.verify_email(token="bogus") is False
    await db.dispose()


@pytest.mark.asyncio
async def test_login_success_and_failures(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, settings, audit)
        tokens = TokenService(session, TokenVault("d" * 64))
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=audit,
            github=github,
            redis=fake_redis,
        )
        svc = AuthService(
            settings=settings,
            db=session,
            redis=fake_redis,
            audit=audit,
            sessions=sessions,
            oauth=oauth,
            tokens=tokens,
        )

        await svc.register(
            email="login@example.com",
            password=STRONG,
            display_name=None,
            ip_address=None,
            user_agent=None,
            request_id=None,
        )

        user, token = await svc.login(
            email="LOGIN@example.com",
            password=STRONG,
            ip_address=None,
            user_agent=None,
            request_id=None,
            remember_me=False,
        )
        assert user.email == "login@example.com"
        assert token

        # Wrong password.
        with pytest.raises(AuthenticationError):
            await svc.login(
                email="login@example.com",
                password="Wrong-Pass-1",
                ip_address=None,
                user_agent=None,
                request_id=None,
                remember_me=False,
            )
        # Unknown email.
        with pytest.raises(AuthenticationError):
            await svc.login(
                email="nobody@example.com",
                password=STRONG,
                ip_address=None,
                user_agent=None,
                request_id=None,
                remember_me=False,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_login_blocked_user(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, settings, audit)
        tokens = TokenService(session, TokenVault("d" * 64))
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=audit,
            github=github,
            redis=fake_redis,
        )
        svc = AuthService(
            settings=settings,
            db=session,
            redis=fake_redis,
            audit=audit,
            sessions=sessions,
            oauth=oauth,
            tokens=tokens,
        )

        user = User(email="blocked@example.com", password_hash="h", status="disabled")
        session.add(user)
        await session.flush()
        with pytest.raises(AuthenticationError):
            await svc.login(
                email="blocked@example.com",
                password=STRONG,
                ip_address=None,
                user_agent=None,
                request_id=None,
                remember_me=False,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_change_password(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, settings, audit)
        tokens = TokenService(session, TokenVault("d" * 64))
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=audit,
            github=github,
            redis=fake_redis,
        )
        svc = AuthService(
            settings=settings,
            db=session,
            redis=fake_redis,
            audit=audit,
            sessions=sessions,
            oauth=oauth,
            tokens=tokens,
        )

        user = await svc.register(
            email="pw@example.com",
            password=STRONG,
            display_name=None,
            ip_address=None,
            user_agent=None,
            request_id=None,
        )
        await svc.change_password(
            user_id=user.id,
            current_password=STRONG,
            new_password="New-Str0ng-2026!",
            ip_address=None,
            user_agent=None,
        )
        user = await session.get(User, user.id)
        assert verify_password("New-Str0ng-2026!", user.password_hash)

        with pytest.raises(AuthenticationError):
            await svc.change_password(
                user_id=user.id,
                current_password="Wrong",
                new_password="X-2026!",
                ip_address=None,
                user_agent=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_unlink_github(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, settings, audit)
        vault = TokenVault("d" * 64)
        tokens = TokenService(session, vault)
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=vault,
            audit=audit,
            github=github,
            redis=fake_redis,
        )
        svc = AuthService(
            settings=settings,
            db=session,
            redis=fake_redis,
            audit=audit,
            sessions=sessions,
            oauth=oauth,
            tokens=tokens,
        )

        user = User(email="u@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(user_id=user.id, github_id=900, login="octocat")
        session.add(account)
        await session.flush()

        await svc.unlink_github(user_id=user.id, github_account_id=account.id)
        assert await session.get(GitHubAccount, account.id) is None

        with pytest.raises(ValidationFailure):
            await svc.unlink_github(user_id=user.id, github_account_id=account.id)
    await db.dispose()
