"""Unit tests: GitHub API client (retries, pagination, rate limits, ETags)."""

from __future__ import annotations

import pytest
import respx

from app.core.config import Settings
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.github.exceptions import GitHubRateLimitError, GitHubUnavailableError


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
        GITHUB_API_BASE_URL="https://api.github.com",
        GITHUB_WEB_BASE_URL="https://github.com",
        GH_RETRY_MAX_ATTEMPTS=3,
        GH_RETRY_BASE_BACKOFF=0.01,
        GH_MAX_RETRY_WAIT_SECONDS=0.02,
    )


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.client = self

    async def set_json(self, key: str, value, ttl: int | None = None) -> None:
        import json

        self.store[key] = json.dumps(value)

    async def get_json(self, key: str):
        import json

        raw = self.store.get(key)
        return json.loads(raw) if raw else None

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.mark.asyncio
async def test_request_retries_transient_errors(respx_mock, settings):
    settings = _settings()
    client = GitHubAPIClient(settings, _FakeRedis())
    respx_mock.get("https://api.github.com/user").mock(
        side_effect=[
            respx.MockResponse(502),
            respx.MockResponse(200, json={"id": 1, "login": "octocat"}),
        ]
    )
    resp = await client.request("GET", "/user", "token")
    assert resp.status_code == 200
    assert resp.json()["login"] == "octocat"
    await client.aclose()


@pytest.mark.asyncio
async def test_rate_limit_raises_after_retries(respx_mock, settings):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user").mock(
        side_effect=[respx.MockResponse(403, headers={"X-RateLimit-Remaining": "0"})] * 3
    )
    with pytest.raises(GitHubRateLimitError):
        await client.request("GET", "/user", "token")
    await client.aclose()


@pytest.mark.asyncio
async def test_pagination_follows_next_link(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user/repos").mock(
        side_effect=[
            respx.MockResponse(
                200,
                json=[
                    {
                        "id": 1,
                        "full_name": "a/repo",
                        "name": "repo",
                        "html_url": "",
                        "owner": {"id": 1, "login": "a"},
                    }
                ],
                headers={
                    "Link": (
                        '<https://api.github.com/user/repos?page=2>; rel="next", '
                        '<https://api.github.com/user/repos?page=3>; rel="last"'
                    )
                },
            ),
            respx.MockResponse(200, json=[]),
        ]
    )
    from app.infrastructure.github.models import GHRepository

    repos = await client.paginate("/user/repos", "token", model=GHRepository)
    assert len(repos) == 1
    assert repos[0].name == "repo"
    assert respx_mock.calls.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_etag_returns_cached_304(respx_mock):
    redis = _FakeRedis()
    client = GitHubAPIClient(_settings(), redis)
    # First call populates cache.
    respx_mock.get("https://api.github.com/user").mock(
        side_effect=[
            respx.MockResponse(200, json={"id": 1, "login": "cached"}, headers={"ETag": '"abc"'}),
            respx.MockResponse(304),
        ]
    )
    first = await client._fetch_with_etag("GET", "/user", "token")
    assert first.json()["login"] == "cached"
    second = await client._fetch_with_etag("GET", "/user", "token")
    assert second.status_code == 200  # served from cache
    assert second.json()["login"] == "cached"
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_raises_after_retries(respx_mock):
    import httpx

    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(GitHubUnavailableError):
        await client.request("GET", "/user", "token")
    await client.aclose()


@pytest.mark.asyncio
async def test_graphql_errors_raised(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.post("https://api.github.com/graphql").mock(
        respx.MockResponse(200, json={"errors": [{"message": "boom"}]})
    )
    from app.infrastructure.github.exceptions import GitHubClientError

    with pytest.raises(GitHubClientError):
        await client.graphql("token", "query { viewer { login } }")
    await client.aclose()
