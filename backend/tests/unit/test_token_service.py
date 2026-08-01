"""Unit tests: TokenService (vault round-trips, expiry, rotation)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application.services.token_service import TokenService
from app.core.config import Settings
from app.core.exceptions import TokenInvalidError
from app.core.security import TokenVault
from app.domain.models.identity import GitHubAccount, User
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


@pytest.fixture
def vault() -> TokenVault:
    return TokenVault("d" * 64)


@pytest.mark.asyncio
async def test_store_and_decrypt_credential(vault):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = TokenService(session, vault)
        user = User(email="u@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(
            user_id=user.id,
            github_id=100,
            login="octocat",
            email="u@example.com",
        )
        session.add(account)
        await session.flush()

        await svc.store_credential(
            github_account_id=account.id,
            user_id=user.id,
            github_id=100,
            access_token="gho_secret",
            refresh_token="ghr_refresh",
            scopes="repo read:user",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        decrypted = await svc.decrypt_credential(account.id)
        assert decrypted.access_token == "gho_secret"
        assert decrypted.refresh_token == "ghr_refresh"
        assert decrypted.scopes == ["repo", "read:user"]

        # access_token_for_user / github_login_for_user
        assert await svc.access_token_for_user(user.id) == "gho_secret"
        assert await svc.github_login_for_user(user.id) == "octocat"

        # revoke_all_for_user deactivates rows.
        await svc.revoke_all_for_user(user.id)
        assert await svc.get_active_credential(account.id) is None
    await db.dispose()


@pytest.mark.asyncio
async def test_store_rotates_previous_credential(vault):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = TokenService(session, vault)
        user = User(email="r@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(user_id=user.id, github_id=101, login="rot")
        session.add(account)
        await session.flush()

        await svc.store_credential(
            github_account_id=account.id, user_id=user.id, github_id=101, access_token="one"
        )
        await svc.store_credential(
            github_account_id=account.id, user_id=user.id, github_id=101, access_token="two"
        )
        cred = await svc.get_active_credential(account.id)
        assert cred is not None
        assert await svc.decrypt_credential(account.id)  # only one active row
    await db.dispose()


@pytest.mark.asyncio
async def test_decrypt_missing_credential_raises(vault):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = TokenService(session, vault)
        with pytest.raises(TokenInvalidError):
            await svc.decrypt_credential(uuid.uuid4())
    await db.dispose()


@pytest.mark.asyncio
async def test_decrypt_expired_access_token(vault):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = TokenService(session, vault)
        user = User(email="e@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(user_id=user.id, github_id=102, login="exp")
        session.add(account)
        await session.flush()

        await svc.store_credential(
            github_account_id=account.id,
            user_id=user.id,
            github_id=102,
            access_token="a",
            refresh_token="r",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        with pytest.raises(TokenInvalidError) as exc:
            await svc.decrypt_credential(account.id)
        assert "refresh required" in str(exc.value)
    await db.dispose()


@pytest.mark.asyncio
async def test_decrypt_expired_without_refresh(vault):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = TokenService(session, vault)
        user = User(email="e2@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(user_id=user.id, github_id=103, login="exp2")
        session.add(account)
        await session.flush()

        await svc.store_credential(
            github_account_id=account.id,
            user_id=user.id,
            github_id=103,
            access_token="a",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        with pytest.raises(TokenInvalidError) as exc:
            await svc.decrypt_credential(account.id)
        assert "expired" in str(exc.value)
    await db.dispose()


@pytest.mark.asyncio
async def test_decrypt_expired_refresh_token(vault):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = TokenService(session, vault)
        user = User(email="e3@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(user_id=user.id, github_id=104, login="exp3")
        session.add(account)
        await session.flush()

        await svc.store_credential(
            github_account_id=account.id,
            user_id=user.id,
            github_id=104,
            access_token="a",
            refresh_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        with pytest.raises(TokenInvalidError) as exc:
            await svc.decrypt_credential(account.id)
        assert "re-authenticate" in str(exc.value)
    await db.dispose()


@pytest.mark.asyncio
async def test_access_token_for_user_without_account(vault):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        svc = TokenService(session, vault)
        user = User(email="na@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        with pytest.raises(TokenInvalidError):
            await svc.access_token_for_user(user.id)
        assert await svc.github_login_for_user(user.id) is None
    await db.dispose()
