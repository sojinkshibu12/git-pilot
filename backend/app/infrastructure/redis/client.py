"""Redis connection management + cache helpers.

A single `RedisClient` container owns the `redis.asyncio` pool. Created at
startup, exposed on `app.state.redis`.
"""

from __future__ import annotations

from typing import Any

import orjson
import redis.asyncio as aioredis

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("redis")


class RedisClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.client: aioredis.Redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
            retry_on_timeout=True,
        )

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception as exc:  # pragma: no cover - infra failure path
            logger.warning("redis_unavailable", error=str(exc))
            return False

    async def close(self) -> None:
        await self.client.aclose()

    # --- serialization helpers ---
    @staticmethod
    def _dumps(value: Any) -> str:
        return orjson.dumps(value).decode()

    @staticmethod
    def _loads(raw: str | bytes) -> Any:
        return orjson.loads(raw)

    # --- cache primitives ---
    async def get_json(self, key: str) -> Any | None:
        raw = await self.client.get(key)
        if raw is None:
            return None
        try:
            return self._loads(raw)
        except orjson.JSONDecodeError:
            logger.warning("cache_decode_failed", key=key)
            await self.client.delete(key)
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        raw = self._dumps(value)
        if ttl:
            await self.client.set(key, raw, ex=ttl)
        else:
            await self.client.set(key, raw)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching `pattern` (SCAN, safe for production)."""
        async for key in self.client.scan_iter(match=pattern, count=500):
            await self.client.delete(key)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        val = await self.client.incr(key)
        if ttl and val == 1:
            await self.client.expire(key, ttl)
        return val

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(key))

    async def ttl(self, key: str) -> int:
        return await self.client.ttl(key)
