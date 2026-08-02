"""Unit tests: OAuthService branches (begin, link flows, exchange errors)."""

from __future__ import annotations

import uuid

import pytest
import respx

from app.application.services.audit_service import AuditService
from app.application.services.oauth_service import OAuthService
from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    GitHubProviderError,
    OAuthStateExpiredError,
    OAuthStateMismatchError,
    PKCEValidationError,
    RedirectUriMismatchError,
)
from app.core.security import TokenVault
from app.domain.models.identity import GitHubAccount, OAuthState, PKCEChallenge, User
from app.infrastructure.db.session import Database
from app.infrastructure.github.models import GHAccessToken, GHUser
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
        GITHUB_SCOPE="read:user user:email repo",
        OAUTH_STATE_TTL_SECONDS=600,
    )


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.mark.asyncio
async def test_begin_generates_url_with_override(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        url, state, method = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address="1.2.3.4",
            user_agent="ua",
            link_to_user_id=None,
            scope_override="repo",
        )
        assert method == "S256"
        assert "code_challenge_method=S256" in url
        assert "scope=repo" in url
        assert "code_challenge=" in url
        assert state

        # State persisted.
        rows = (await session.scalars(select(OAuthState))).all()
        assert len(rows) == 1
        assert rows[0].link_to_user_id is None
    await db.dispose()


from sqlalchemy import select  # noqa: E402


@pytest.mark.asyncio
async def test_begin_with_link_to_user(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        uid = uuid.uuid4()
        await oauth.begin(
            session_id=uuid.uuid4(),
            user_id=uid,
            ip_address=None,
            user_agent=None,
            link_to_user_id=uid,
        )
        row = await session.scalar(select(OAuthState))
        assert row.link_to_user_id == uid
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_error_non_denied_raises(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        with pytest.raises(GitHubProviderError):
            await oauth.handle_callback(
                state="s",
                code=None,
                error="server_error",
                error_description="x",
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
        # Missing code.
        with pytest.raises(OAuthStateMismatchError):
            await oauth.handle_callback(
                state="s",
                code=None,
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
        # Unknown state.
        with pytest.raises(OAuthStateMismatchError):
            await oauth.handle_callback(
                state="nope",
                code="code",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_begin_authorize_link_flow(fake_redis):
    """Simulate the Password→GitHub linking flow end-to-end (no exchange needed)."""
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        github.users[777] = {
            "id": 777,
            "login": "linked",
            "name": "Linked",
            "email": "linked@example.com",
            "html_url": "",
            "type": "User",
        }
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        target = User(email="t@example.com", password_hash="h")
        session.add(target)
        await session.flush()

        # begin() → generate valid state + PKCE so we can drive the callback.
        url, state, _method = await oauth.begin(
            session_id=uuid.uuid4(),
            user_id=target.id,
            ip_address=None,
            user_agent=None,
            link_to_user_id=target.id,
        )
        from urllib.parse import parse_qs, urlparse

        _challenge = parse_qs(urlparse(url).query)["code_challenge"][0]

        with respx.mock:
            respx.post("https://github.com/login/oauth/access_token").mock(
                respx.MockResponse(200, json={"access_token": "gho_tok", "token_type": "bearer"})
            )
            user, account, token = await oauth.handle_callback(
                state=state,
                code="a-code",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id="req",
            )
        assert user.id == target.id
        assert account.login == "linked"
        assert token == "gho_tok"
    await db.dispose()


@pytest.mark.asyncio
async def test_complete_link_password_check(fake_redis):
    from app.core.security import hash_password

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        target = User(
            email="pw@example.com",
            password_hash=hash_password("Str0ng-Passw0rd!", settings),
        )
        session.add(target)
        await session.flush()

        # No password on target → auth error.
        target2 = User(email="nopw@example.com", password_hash=None)
        session.add(target2)
        await session.flush()
        with pytest.raises(AuthenticationError):
            await oauth.complete_link(
                link_token="x",
                password="y",
                user_id=target2.id,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
        # Wrong password.
        with pytest.raises(AuthenticationError):
            await oauth.complete_link(
                link_token="x",
                password="wrong",
                user_id=target.id,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
        # Missing pending link.
        with pytest.raises(OAuthStateExpiredError):
            await oauth.complete_link(
                link_token="missing",
                password="Str0ng-Passw0rd!",
                user_id=target.id,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_store_credential_with_expirations(fake_redis):
    from app.application.services.oauth_service import TokenServiceStub
    from app.infrastructure.github.models import GHAccessToken

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        user = User(email="cred@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(user_id=user.id, github_id=1, login="c")
        session.add(account)
        await session.flush()

        token_data = GHAccessToken(
            access_token="gho_x",
            refresh_token="ghr_y",
            scope="repo",
            expires_in=3600,
            refresh_token_expires_in=7200,
        )
        cred = await oauth._store_credential(account, token_data)
        assert cred.access_token_encrypted
        assert cred.expires_at is not None
        assert cred.refresh_expires_at is not None

        # Via stub too.
        stub = TokenServiceStub(session, TokenVault("d" * 64))
        cred2 = await stub.store_credential(
            github_account_id=account.id,
            user_id=user.id,
            github_id=1,
            access_token="gho_z",
            scopes="repo",
        )
        assert cred2.is_active is True
    await db.dispose()


@pytest.mark.asyncio
async def test_exchange_code_error_status(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        with respx.mock:
            respx.post("https://github.com/login/oauth/access_token").mock(
                respx.MockResponse(500, json={})
            )
            with pytest.raises(GitHubProviderError):
                await oauth._exchange_code("code", "verifier", "uri")
    await db.dispose()


@pytest.mark.asyncio
async def test_resolve_email_fallback_and_error(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        # gh_user.email present → returned directly.
        with_email = GHUser(id=2, login="l", email="x@example.com")
        assert await oauth._resolve_email(with_email, "tok") == "x@example.com"

        # No gh_user.email → get_primary_email.
        github.emails = [{"email": "p@e.com", "primary": True, "verified": True}]

        no_email = GHUser(id=1, login="l", email=None)
        assert await oauth._resolve_email(no_email, "tok") == "p@e.com"
    await db.dispose()


@pytest.mark.asyncio
async def test_redis_none_paths():
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=None,
        )
        # _park_pending_link with redis=None returns token without storing.
        gh = GHUser(id=1, login="l")
        tok = await oauth._park_pending_link(uuid.uuid4(), GHAccessToken(access_token="a"), gh, "e")
        assert tok
        assert await oauth._redis_get_pending_link("anything") is None
        await oauth._redis_delete_pending_link("anything")  # no-op
        # complete_link with no pending link (redis None) raises.
        from app.core.security import hash_password

        target = User(
            email="x@example.com",
            password_hash=hash_password("Str0ng-Passw0rd!", settings),
        )
        session.add(target)
        await session.flush()
        with pytest.raises(OAuthStateExpiredError):
            await oauth.complete_link(
                link_token="t",
                password="Str0ng-Passw0rd!",
                user_id=target.id,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_user_mismatch_pending(fake_redis):
    from app.core.security import hash_password

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        target = User(
            email="mm@example.com", password_hash=hash_password("Str0ng-Passw0rd!", settings)
        )
        session.add(target)
        await session.flush()

        # Park a pending link for a different user.
        link_token = await oauth._park_pending_link(
            uuid.uuid4(), GHAccessToken(access_token="a"), GHUser(id=1, login="l"), "e@example.com"
        )
        # complete_link with wrong user → mismatch error.
        with pytest.raises(OAuthStateMismatchError):
            await oauth.complete_link(
                link_token=link_token,
                password="Str0ng-Passw0rd!",
                user_id=target.id,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_expired_state(fake_redis):
    from datetime import UTC, datetime, timedelta

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=FakeGitHubClient(settings),
            redis=fake_redis,
        )
        _url, state, _m = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        row = await session.scalar(select(OAuthState))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.flush()
        with pytest.raises(OAuthStateExpiredError):
            await oauth.handle_callback(
                state=state,
                code="c",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_redirect_mismatch(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=FakeGitHubClient(settings),
            redis=fake_redis,
        )
        _url, state, _m = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        row = await session.scalar(select(OAuthState))
        row.redirect_uri = "https://evil.example/cb"
        await session.flush()
        with pytest.raises(RedirectUriMismatchError):
            await oauth.handle_callback(
                state=state,
                code="c",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_replay_consumed(fake_redis):
    from datetime import UTC, datetime

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=FakeGitHubClient(settings),
            redis=fake_redis,
        )
        _url, state, _m = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        row = await session.scalar(select(OAuthState))
        row.consumed_at = datetime.now(UTC)
        await session.flush()
        with pytest.raises(OAuthStateMismatchError):
            await oauth.handle_callback(
                state=state,
                code="c",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_pkce_missing_and_mismatch(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=FakeGitHubClient(settings),
            redis=fake_redis,
        )
        _url, state, _m = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        # Delete the PKCE record → missing.
        pkce = await session.scalar(select(PKCEChallenge))
        await session.delete(pkce)
        await session.flush()
        with pytest.raises(PKCEValidationError):
            await oauth.handle_callback(
                state=state,
                code="c",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
        # Corrupt the stored hash → mismatch.
        _url2, state2, _m2 = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        pkce2 = await session.scalar(select(PKCEChallenge))
        pkce2.code_challenge_hash = "0" * 64
        await session.flush()
        with pytest.raises(PKCEValidationError):
            await oauth.handle_callback(
                state=state2,
                code="c",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_exchange_error(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=FakeGitHubClient(settings),
            redis=fake_redis,
        )
        _url, state, _m = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        with respx.mock:
            respx.post("https://github.com/login/oauth/access_token").mock(
                respx.MockResponse(200, json={"access_token": "x", "error": "bad_verifier"})
            )
            with pytest.raises(GitHubProviderError):
                await oauth.handle_callback(
                    state=state,
                    code="c",
                    error=None,
                    error_description=None,
                    ip_address=None,
                    user_agent=None,
                    request_id=None,
                )
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_existing_account_login(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        github.users[999] = {
            "id": 999,
            "login": "returning",
            "name": "Returning",
            "email": "r@e.com",
            "avatar_url": "https://a/1",
            "html_url": "https://github.com/returning",
            "location": "NYC",
            "bio": "hi",
            "company": "ACME",
            "type": "User",
        }
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        user = User(email="r@e.com", password_hash="h")
        session.add(user)
        await session.flush()
        account = GitHubAccount(
            user_id=user.id,
            github_id=999,
            login="old",
            email="r@e.com",
        )
        session.add(account)
        await session.flush()

        _url, state, _m = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        with respx.mock:
            respx.post("https://github.com/login/oauth/access_token").mock(
                respx.MockResponse(200, json={"access_token": "gho_ret", "token_type": "bearer"})
            )
            got_user, got_account, token = await oauth.handle_callback(
                state=state,
                code="c",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
        assert got_user.id == user.id
        assert got_account.login == "returning"
        assert token == "gho_ret"
    await db.dispose()


@pytest.mark.asyncio
async def test_callback_new_user_registration(fake_redis):
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        github.users[1001] = {
            "id": 1001,
            "login": "newbie",
            "name": "Newbie",
            "email": "n@e.com",
            "avatar_url": None,
            "html_url": "https://github.com/newbie",
            "location": None,
            "bio": None,
            "company": None,
            "type": "User",
        }
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        _url, state, _m = await oauth.begin(
            session_id=None,
            user_id=None,
            ip_address=None,
            user_agent=None,
        )
        with respx.mock:
            respx.post("https://github.com/login/oauth/access_token").mock(
                respx.MockResponse(200, json={"access_token": "gho_new", "token_type": "bearer"})
            )
            user, account, token = await oauth.handle_callback(
                state=state,
                code="c",
                error=None,
                error_description=None,
                ip_address=None,
                user_agent=None,
                request_id=None,
            )
        assert user.email == "n@e.com"
        assert account.login == "newbie"
        assert token == "gho_new"
        assert user.status == "active"
    await db.dispose()


@pytest.mark.asyncio
async def test_complete_link_success(fake_redis):
    from app.core.security import hash_password

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        settings = _settings()
        github = FakeGitHubClient(settings)
        oauth = OAuthService(
            settings=settings,
            db=session,
            vault=TokenVault("d" * 64),
            audit=AuditService(session),
            github=github,
            redis=fake_redis,
        )
        target = User(
            email="cl@example.com", password_hash=hash_password("Str0ng-Passw0rd!", settings)
        )
        session.add(target)
        await session.flush()

        gh = GHUser(id=42, login="linker", email="cl@example.com")
        token_data = GHAccessToken(access_token="gho_l", refresh_token="ghr_l")
        link_token = await oauth._park_pending_link(target.id, token_data, gh, "cl@example.com")
        account = await oauth.complete_link(
            link_token=link_token,
            password="Str0ng-Passw0rd!",
            user_id=target.id,
            ip_address=None,
            user_agent=None,
            request_id=None,
        )
        assert account.user_id == target.id
        assert account.login == "linker"
        assert await fake_redis.get_json("gp:link:" + link_token) is None
    await db.dispose()
