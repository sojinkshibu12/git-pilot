"""Unit tests: RedisClient serialization + cache primitives (mocked transport)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.redis.client import RedisClient


def _settings() -> Settings:
    return Settings(
        APP_ENV="testing",
        SECRET_KEY="k" * 32,
        TOKEN_ENCRYPTION_KEY="d" * 64,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        GITHUB_CLIENT_ID="cid",
        GITHUB_CLIENT_SECRET="csec",
        GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
    )


class _FakeRedisTransport:
    """Minimal stand-in for redis.asyncio.Redis."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ping = AsyncMock(return_value=True)
        self.ping.side_effect = None

    async def aclose(self) -> None:
        return None

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)

    async def scan_iter(self, match: str = "*", count: int = 100):
        import fnmatch

        for key in [k for k in self.data if fnmatch.fnmatch(k, match)]:
            yield key

    async def incr(self, key: str) -> int:
        val = int(self.data.get(key, 0)) + 1
        self.data[key] = str(val)
        return val

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def exists(self, key: str) -> int:
        return 1 if key in self.data else 0

    async def ttl(self, key: str) -> int:
        return 300 if key in self.data else -2


def _make_client() -> tuple[RedisClient, _FakeRedisTransport]:
    transport = _FakeRedisTransport()
    with patch(
        "app.infrastructure.redis.client.aioredis.from_url",
        return_value=transport,
    ):
        client = RedisClient(_settings())
    return client, transport


@pytest.mark.asyncio
async def test_ping_ok():
    client, transport = _make_client()
    transport.ping = AsyncMock(return_value=True)
    assert await client.ping() is True
    await client.close()


@pytest.mark.asyncio
async def test_ping_failure_returns_false():
    client, transport = _make_client()
    transport.ping = AsyncMock(side_effect=Exception("down"))
    assert await client.ping() is False
    await client.close()


@pytest.mark.asyncio
async def test_close_called():
    client, transport = _make_client()
    transport.aclose = AsyncMock()
    await client.close()
    transport.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_json_and_get_json():
    client, transport = _make_client()
    await client.set_json("key", {"a": 1}, ttl=60)
    assert transport.data["key"] == '{"a":1}'
    assert await client.get_json("key") == {"a": 1}


@pytest.mark.asyncio
async def test_set_json_no_ttl():
    client, transport = _make_client()
    await client.set_json("key", [1, 2])
    assert await client.get_json("key") == [1, 2]


@pytest.mark.asyncio
async def test_get_json_missing_returns_none():
    client, _transport = _make_client()
    assert await client.get_json("nope") is None


@pytest.mark.asyncio
async def test_get_json_corrupt_deletes_key():
    client, transport = _make_client()
    transport.data["bad"] = "not-json{"
    assert await client.get_json("bad") is None
    assert "bad" not in transport.data


@pytest.mark.asyncio
async def test_delete():
    client, transport = _make_client()
    transport.data["k"] = "v"
    await client.delete("k")
    assert "k" not in transport.data


@pytest.mark.asyncio
async def test_delete_pattern():
    client, transport = _make_client()
    transport.data = {"a:1": "x", "a:2": "y", "b:1": "z"}
    await client.delete_pattern("a:*")
    assert set(transport.data) == {"b:1"}


@pytest.mark.asyncio
async def test_incr_with_ttl():
    client, transport = _make_client()
    transport.expire = AsyncMock()
    assert await client.incr("counter", ttl=60) == 1
    transport.expire.assert_awaited_once_with("counter", 60)
    assert await client.incr("counter") == 2
    assert transport.data["counter"] == "2"


@pytest.mark.asyncio
async def test_incr_no_ttl():
    client, transport = _make_client()
    transport.expire = AsyncMock()
    assert await client.incr("n") == 1
    transport.expire.assert_not_called()


@pytest.mark.asyncio
async def test_exists_and_ttl():
    client, transport = _make_client()
    transport.data["present"] = "v"
    assert await client.exists("present") is True
    assert await client.exists("absent") is False
    assert await client.ttl("present") == 300
    assert await client.ttl("absent") == -2
