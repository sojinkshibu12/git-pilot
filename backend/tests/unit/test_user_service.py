"""Unit tests: UserService (profile, preferences, accounts, security overview)."""

from __future__ import annotations

import uuid

import pytest

from app.application.services.audit_service import AuditService
from app.application.services.session_service import SessionService
from app.application.services.token_service import TokenService
from app.application.services.user_service import UserService
from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.security import TokenVault
from app.domain.models.identity import GitHubAccount, User
from app.infrastructure.db.session import Database
from tests.conftest import FakeGitHubClient, FakeRedis


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
async def test_profile_crud_and_preferences(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, _settings(), audit)
        tokens = TokenService(session, TokenVault("d" * 64))
        svc = UserService(
            db=session,
            audit=audit,
            sessions=sessions,
            tokens=tokens,
            github=FakeGitHubClient(_settings()),
        )

        user = User(email="u@example.com", password_hash="h")
        session.add(user)
        await session.flush()

        profile = await svc.get_profile(user.id)
        assert profile.email == "u@example.com"

        with pytest.raises(NotFoundError):
            await svc.get_profile(uuid.uuid4())

        updated = await svc.update_profile(user.id, display_name="New", locale="fr")
        assert updated.display_name == "New"
        assert updated.locale == "fr"

        with pytest.raises(NotFoundError):
            await svc.update_profile(uuid.uuid4(), display_name="X")

        prefs = await svc.get_preferences(user.id)
        assert prefs.theme == "system"
        prefs2 = await svc.get_preferences(user.id)
        assert prefs2.id == prefs.id

        changed = await svc.update_preferences(user.id, theme="dark", timezone="UTC")
        assert changed.theme == "dark"
        assert changed.timezone == "UTC"
    await db.dispose()


@pytest.mark.asyncio
async def test_connected_accounts_and_security(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, _settings(), audit)
        tokens = TokenService(session, TokenVault("d" * 64))
        svc = UserService(
            db=session,
            audit=audit,
            sessions=sessions,
            tokens=tokens,
            github=FakeGitHubClient(_settings()),
        )

        user = User(email="a@example.com", password_hash="h", email_verified=True)
        session.add(user)
        await session.flush()
        account = GitHubAccount(
            user_id=user.id,
            github_id=500,
            login="octocat",
            email="a@example.com",
            email_verified=True,
        )
        session.add(account)
        await session.flush()
        await tokens.store_credential(
            github_account_id=account.id,
            user_id=user.id,
            github_id=500,
            access_token="gho_tok",
        )

        accounts = await svc.list_connected_accounts(user.id)
        github_row = next(a for a in accounts if a["provider"].value == "github")
        assert github_row["connected"] is True
        assert github_row["login"] == "octocat"
        other = next(a for a in accounts if a["provider"].value == "google")
        assert other["connected"] is False

        # No accounts at all → all disconnected.
        user2 = User(email="b@example.com", password_hash="h")
        session.add(user2)
        await session.flush()
        empty = await svc.list_connected_accounts(user2.id)
        assert all(a["connected"] is False for a in empty)

        overview = await svc.security_overview(user.id)
        assert overview["has_password"] is True
        assert overview["email_verified"] is True
        assert overview["active_sessions_count"] is False
    await db.dispose()


@pytest.mark.asyncio
async def test_github_profile_from_api(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        audit = AuditService(session)
        sessions = SessionService(session, fake_redis, _settings(), audit)
        tokens = TokenService(session, TokenVault("d" * 64))
        github = FakeGitHubClient(_settings())
        github.users[1] = {"id": 1, "login": "octocat", "name": "O"}

        svc = UserService(db=session, audit=audit, sessions=sessions, tokens=tokens, github=github)

        # No linked account → None.
        user = User(email="c@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        assert await svc.github_profile_from_api(user.id) is None

        account = GitHubAccount(user_id=user.id, github_id=1, login="octocat")
        session.add(account)
        await session.flush()
        await tokens.store_credential(
            github_account_id=account.id, user_id=user.id, github_id=1, access_token="gho_tok"
        )
        profile = await svc.github_profile_from_api(user.id)
        assert profile is not None
        assert profile["login"] == "octocat"
    await db.dispose()
