"""Shared test fixtures.

- In-memory SQLite (async) via the `Database` container
- Fake in-process Redis (dict-backed) so tests run without a Redis server
- Fake GitHub API client (recorded responses) so tests run without network
- A TestClient against the real `make_app()` application
"""
from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings  # noqa: E402


def _test_settings() -> Settings:
    return Settings(
        APP_ENV="testing",
        SECRET_KEY="test-secret-key-0123456789abcdef0123456789abcdef",
        TOKEN_ENCRYPTION_KEY="a" * 64,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://fake",
        GITHUB_CLIENT_ID="test-client-id",
        GITHUB_CLIENT_SECRET="test-client-secret",
        GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
        GITHUB_API_BASE_URL="https://api.github.com",
        GITHUB_WEB_BASE_URL="https://github.com",
        CORS_ORIGINS=["http://localhost:3000"],
    )


class FakeRedis:
    """Minimal dict-backed Redis substitute (no expiry enforcement in tests)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._ttl: dict[str, int] = {}
        self.client = self

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = value
        if ex:
            self._ttl[key] = ex

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._ttl.pop(key, None)

    async def expire(self, key: str, seconds: int) -> None:
        self._ttl[key] = seconds

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, -1)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        if ttl and val == 1:
            self._ttl[key] = ttl
        return val

    async def set_json(self, key: str, value, ttl: int | None = None) -> None:
        import orjson

        self._data[key] = orjson.dumps(value).decode()
        if ttl:
            self._ttl[key] = ttl

    async def get_json(self, key: str):
        import orjson

        raw = self._data.get(key)
        if raw is None:
            return None
        try:
            return orjson.loads(raw)
        except orjson.JSONDecodeError:
            self._data.pop(key, None)
            self._ttl.pop(key, None)
            return None

    async def delete_pattern(self, pattern: str) -> None:
        import fnmatch

        for key in [k for k in self._data if fnmatch.fnmatch(k, pattern)]:
            self._data.pop(key, None)
            self._ttl.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def smembers(self, key: str) -> set[str]:
        raw = self._data.get(key)
        return set(raw.split(",")) if raw else set()

    async def sadd(self, key: str, *values: str) -> None:
        existing = await self.smembers(key)
        existing.update(values)
        self._data[key] = ",".join(existing)

    async def srem(self, key: str, *values: str) -> None:
        existing = await self.smembers(key)
        for v in values:
            existing.discard(v)
        self._data[key] = ",".join(existing) if existing else ""


class FakeGitHubClient:
    """Stubbed GitHub client with scriptable responses."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users: dict[int, dict] = {}
        self.emails: list[dict] = []
        self.orgs: list[dict] = []
        self.repos: list[dict] = []
        self.calls: list[tuple[str, str]] = []

    async def get_user(self, token: str) -> object:
        self.calls.append(("GET", "/user"))
        gh = self.users.get(_tok_id(token), {})
        from app.infrastructure.github.models import GHUser

        return GHUser.model_validate(gh)

    async def get_user_emails(self, token: str) -> list:
        from app.infrastructure.github.models import GHEmail

        return [GHEmail.model_validate(e) for e in self.emails]

    async def get_primary_email(self, token: str) -> str | None:
        for e in self.emails:
            if e["primary"] and e["verified"]:
                return e["email"]
        for e in self.emails:
            if e["primary"]:
                return e["email"]
        return None

    async def list_organizations(self, token: str) -> list:
        from app.infrastructure.github.models import GHOrganization

        return [GHOrganization.model_validate(o) for o in self.orgs]

    async def list_repositories(self, token: str) -> list:
        from app.infrastructure.github.models import GHRepository

        return [GHRepository.model_validate(r) for r in self.repos]

    async def list_repositories_page(self, token: str, *, page: int = 1, per_page: int = 30, **kwargs) -> object:
        from app.infrastructure.github.models import GHPaged, GHRepository

        start = (page - 1) * per_page
        items = [GHRepository.model_validate(r) for r in self.repos[start : start + per_page]]
        total = len(self.repos)
        return GHPaged(
            items=items,
            next_page=None,
            total_count=total,
        )

    async def get_commit_count_for_user(self, token: str, owner: str, repo: str, author: str) -> int:
        return 0

    async def get_contributions_summary(self, token: str, login: str) -> dict:
        return {"commits": 0, "pull_requests": 0, "issues": 0, "reviews": 0, "total": 0}

    async def get_contribution_calendar(self, token: str, login: str, from_date, to_date) -> dict:
        return {"days": [], "total": 0, "breakdown": {"commits": 0, "pull_requests": 0, "issues": 0, "reviews": 0, "repositories": 0, "actions": 0}}

    async def get_commit_contribution_days(self, token: str, login: str, from_date, to_date) -> tuple[dict, dict]:
        return {}, {}

    async def get_issue_contribution_days(self, token: str, login: str, from_date, to_date, **kwargs) -> dict:
        return {}

    async def get_repository_creation_days(self, token: str, login: str, from_date, to_date, **kwargs) -> dict:
        return {}

    async def get_action_days(self, token: str, login: str, from_date, to_date, **kwargs) -> dict:
        return {}

    async def graphql(self, token: str, query: str, variables: dict | None = None) -> dict:
        return {}

    async def get_repository(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHRepository

        return GHRepository.model_validate({"id": 1, "full_name": f"{owner}/{repo}", "name": repo, "html_url": "", "owner": {"id": 1, "login": owner}})

    async def aclose(self) -> None:
        return None


def _tok_id(token: str) -> int:
    return int(hash(token) % 100000)


@pytest.fixture
def settings() -> Settings:
    return _test_settings()


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def vault(settings: Settings):
    from app.core.security import configure_vault

    return configure_vault(settings)


@pytest.fixture
def fake_github(settings: Settings) -> FakeGitHubClient:
    return FakeGitHubClient(settings)


@pytest.fixture
def app(settings: Settings, fake_redis: FakeRedis, fake_github: FakeGitHubClient):
    from app.main import make_app

    app = make_app(settings)
    app.state.redis = fake_redis  # type: ignore[attr-defined]
    app.state.github = fake_github  # type: ignore[attr-defined]
    app.state.vault = None  # replaced below

    from app.core.security import TokenVault

    app.state.vault = TokenVault(settings.TOKEN_ENCRYPTION_KEY)  # type: ignore[attr-defined]

    async def _init():
        from app.infrastructure.db.session import Database

        db = Database(settings)
        await db.init_db()
        app.state.db = db  # type: ignore[attr-defined]

    import asyncio

    asyncio.run(_init())
    return app


@pytest.fixture
async def client(app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
