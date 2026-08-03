"""Unit tests: GitHubAppAuthService (JWT → installation → access token)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.application.services.github_app_auth_service import (
    GitHubAppAuthError,
    GitHubAppAuthService,
)
from app.core.config import Settings
from app.infrastructure.github.exceptions import GitHubNotFoundError


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _app_settings(*, fixed_install: int | None = None, enabled: bool = True) -> Settings:
    return Settings(
        APP_ENV="testing",
        SECRET_KEY="k" * 32,
        TOKEN_ENCRYPTION_KEY="d" * 64,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://fake",
        GITHUB_CLIENT_ID="cid",
        GITHUB_CLIENT_SECRET="csec",
        GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
        GITHUB_APP_TYPE="github_app" if enabled else "oauth_app",
        GITHUB_APP_ID=12345,
        GITHUB_APP_PRIVATE_KEY=_rsa_pem(),
        GITHUB_APP_INSTALLATION_ID=fixed_install,
    )


class _FakeGithubClient:
    """Records `request()` calls; returns scripted JSON responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.installation_by_owner: dict[str, dict[str, Any]] = {}
        self.installations_list: list[dict[str, Any]] = []
        self.token_response: dict[str, Any] = {
            "token": "ghs_install_token",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
        self.repositories_response: dict[str, Any] = {
            "repositories": [
                {
                    "id": 1,
                    "full_name": "acme/repo",
                    "name": "repo",
                    "html_url": "https://github.com/acme/repo",
                    "owner": {"id": 1, "login": "acme"},
                }
            ]
        }
        self.fail_all = False

    async def request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        etag: str | None = None,
        retries: int | None = None,
    ):
        self.calls.append((method, path, token))
        if self.fail_all:
            raise GitHubNotFoundError("gone")

        if method == "POST" and "/access_tokens" in path:
            return _Resp(self.token_response)
        if path == "/installation/repositories":
            return _Resp(self.repositories_response)
        if path.startswith("/app/installations"):
            if self.installations_list:
                return _Resp(self.installations_list)
            raise GitHubNotFoundError("no list")
        if path.startswith(("/repos/", "/orgs/", "/users/")):
            owner = path.split("/")[2]
            found = self.installation_by_owner.get(owner.lower())
            if found:
                return _Resp(found)
            raise GitHubNotFoundError("not installed")
        raise AssertionError(f"Unexpected request: {method} {path}")


class _Resp:
    def __init__(self, json: dict[str, Any] | list[Any]) -> None:
        self._json = json
        self.status_code = 200

    def json(self):
        return self._json


@pytest.fixture
def fake_github() -> _FakeGithubClient:
    return _FakeGithubClient()


@pytest.fixture
def fake_redis():
    from tests.conftest import FakeRedis

    return FakeRedis()


def _svc(settings: Settings, github, redis) -> GitHubAppAuthService:
    return GitHubAppAuthService(settings=settings, github=github, redis=redis)


@pytest.mark.asyncio
async def test_create_app_jwt(fake_github, fake_redis):
    svc = _svc(_app_settings(), fake_github, fake_redis)
    jwt = svc.create_app_jwt()
    assert jwt.count(".") == 2
    assert len(jwt) > 20


@pytest.mark.asyncio
async def test_create_app_jwt_missing_key(fake_github, fake_redis):
    settings = _app_settings()
    settings.GITHUB_APP_PRIVATE_KEY = None  # type: ignore[assignment]
    svc = _svc(settings, fake_github, fake_redis)
    with pytest.raises(GitHubAppAuthError):
        svc.create_app_jwt()


@pytest.mark.asyncio
async def test_installation_token_fixed_install(fake_github, fake_redis):
    settings = _app_settings(fixed_install=999)
    svc = _svc(settings, fake_github, fake_redis)

    token = await svc.installation_token_for("acme", "repo")
    assert token == "ghs_install_token"

    # Fixed install → no resolution calls, only the token POST.
    posts = [c for c in fake_github.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert "/app/installations/999/access_tokens" in posts[0][1]


@pytest.mark.asyncio
async def test_installation_token_resolves_by_repo(fake_github, fake_redis):
    fake_github.installation_by_owner["acme"] = {
        "id": 42,
        "app_id": 12345,
        "account": {"id": 1, "login": "acme"},
        "target_type": "User",
    }
    svc = _svc(_app_settings(), fake_github, fake_redis)

    token = await svc.installation_token_for("acme", "repo")
    assert token == "ghs_install_token"
    # Resolution hit /repos/acme/repo/installation
    assert any(c[0] == "GET" and "acme/repo/installation" in c[1] for c in fake_github.calls)


@pytest.mark.asyncio
async def test_installation_token_resolves_by_list(fake_github, fake_redis):
    fake_github.installations_list = [
        {
            "id": 7,
            "account": {"id": 1, "login": "acme"},
            "target_type": "Organization",
        }
    ]
    svc = _svc(_app_settings(), fake_github, fake_redis)
    token = await svc.installation_token_for("acme", "repo")
    assert token == "ghs_install_token"


@pytest.mark.asyncio
async def test_installation_token_not_installed(fake_github, fake_redis):
    svc = _svc(_app_settings(), fake_github, fake_redis)
    with pytest.raises(GitHubAppAuthError):
        await svc.installation_token_for("unknown", "repo")


@pytest.mark.asyncio
async def test_installation_token_cached(fake_github, fake_redis):
    settings = _app_settings(fixed_install=999)
    svc = _svc(settings, fake_github, fake_redis)

    t1 = await svc.installation_token_for("acme", "repo")
    t2 = await svc.installation_token_for("acme", "repo")
    assert t1 == t2 == "ghs_install_token"
    posts = [c for c in fake_github.calls if c[0] == "POST"]
    assert len(posts) == 1  # cached on second call


@pytest.mark.asyncio
async def test_installation_token_reissued_when_expired(fake_github, fake_redis):
    settings = _app_settings(fixed_install=999)
    svc = _svc(settings, fake_github, fake_redis)

    await svc.installation_token_for("acme", "repo")

    # Force a stale cached entry.
    await fake_redis.set_json(
        "gp:install-token:999",
        {
            "token": "stale_token",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
        ttl=10,
    )
    token = await svc.installation_token_for("acme", "repo")
    assert token == "ghs_install_token"


@pytest.mark.asyncio
async def test_list_installation_repositories(fake_github, fake_redis):
    settings = _app_settings(fixed_install=999)
    svc = _svc(settings, fake_github, fake_redis)
    repos = await svc.list_installation_repositories(owner="acme", repo="repo")
    assert repos[0].full_name == "acme/repo"
    assert any(c[1] == "/installation/repositories" for c in fake_github.calls)


@pytest.mark.asyncio
async def test_installation_id_cached(fake_github, fake_redis):
    fake_github.installation_by_owner["acme"] = {
        "id": 42,
        "account": {"id": 1, "login": "acme"},
    }
    svc = _svc(_app_settings(), fake_github, fake_redis)
    first = await svc.installation_id_for("acme", "repo")
    second = await svc.installation_id_for("acme", "repo")
    assert first == second == 42
    resolutions = [c for c in fake_github.calls if c[0] == "GET"]
    assert len(resolutions) == 1  # cached after first resolve


def test_settings_require_app_fields_when_type_github_app():
    with pytest.raises(ValueError, match="GITHUB_APP_ID"):
        Settings(
            APP_ENV="testing",
            SECRET_KEY="k" * 32,
            TOKEN_ENCRYPTION_KEY="d" * 64,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REDIS_URL="redis://fake",
            GITHUB_CLIENT_ID="cid",
            GITHUB_CLIENT_SECRET="csec",
            GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
            GITHUB_APP_TYPE="github_app",
            GITHUB_APP_ID=None,
            GITHUB_APP_PRIVATE_KEY=_rsa_pem(),
        )


def test_settings_require_private_key_when_type_github_app():
    with pytest.raises(ValueError, match="GITHUB_APP_PRIVATE_KEY"):
        Settings(
            APP_ENV="testing",
            SECRET_KEY="k" * 32,
            TOKEN_ENCRYPTION_KEY="d" * 64,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REDIS_URL="redis://fake",
            GITHUB_CLIENT_ID="cid",
            GITHUB_CLIENT_SECRET="csec",
            GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
            GITHUB_APP_TYPE="github_app",
            GITHUB_APP_ID=123,
            GITHUB_APP_PRIVATE_KEY=None,
        )


def test_github_app_enabled_property():
    settings = _app_settings()
    assert settings.github_app_enabled is True
    assert settings.GITHUB_APP_TYPE == "github_app"

    settings2 = _app_settings(enabled=False)
    assert settings2.github_app_enabled is False


def test_github_private_key_resolves_path():
    import tempfile
    from pathlib import Path

    pem = _rsa_pem()
    with tempfile.TemporaryDirectory() as tmp:
        key_file = Path(tmp) / "app.pem"
        key_file.write_text(pem, encoding="utf-8")
        settings = _app_settings()
        settings.GITHUB_APP_PRIVATE_KEY = str(key_file)  # type: ignore[assignment]
        assert settings.github_private_key() == pem


def test_github_private_key_returns_contents_directly():
    pem = _rsa_pem()
    settings = _app_settings()
    settings.GITHUB_APP_PRIVATE_KEY = pem  # type: ignore[assignment]
    assert settings.github_private_key() == pem.strip()


def test_empty_int_fields_are_none():
    settings = Settings(
        APP_ENV="testing",
        SECRET_KEY="k" * 32,
        TOKEN_ENCRYPTION_KEY="d" * 64,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://fake",
        GITHUB_CLIENT_ID="cid",
        GITHUB_CLIENT_SECRET="csec",
        GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
        GITHUB_APP_TYPE="github_app",
        GITHUB_APP_ID=123,
        GITHUB_APP_PRIVATE_KEY=_rsa_pem(),
        GITHUB_APP_INSTALLATION_ID="",
    )
    assert settings.GITHUB_APP_INSTALLATION_ID is None
