"""Redis-backed rate limiter (fixed window with INCR + EXPIRE).

Used for login endpoints (per IP + per account), the OAuth callback, and global
API protection. Prevents brute-force credential stuffing and OAuth state
replay attacks.
"""
from __future__ import annotations

from app.core.exceptions import RateLimitExceeded
from app.infrastructure.redis.client import RedisClient


class RateLimiter:
    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    def _key(self, bucket: str, identifier: str) -> str:
        return f"gp:rl:{bucket}:{identifier}"

    async def check(self, bucket: str, identifier: str, limit: int, window_seconds: int) -> None:
        key = self._key(bucket, identifier)
        count = await self._redis.incr(key, ttl=window_seconds)
        if count > limit:
            ttl = await self._redis.ttl(key)
            raise RateLimitExceeded(
                "Too many requests. Try again shortly.",
                retry_after_seconds=max(ttl, 1),
            )

    async def reset(self, bucket: str, identifier: str) -> None:
        await self._redis.delete(self._key(bucket, identifier))
