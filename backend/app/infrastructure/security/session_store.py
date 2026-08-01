"""Redis-backed server-side session store.

Sessions live in Redis (fast, horizontal-scale friendly) with the durable
authoritative record in PostgreSQL. The browser cookie holds only an opaque
session token; the token hash is what we store, never the raw token.

Keys:
    gp:session:<sha256(token)>  → JSON payload (user id, expiry, csrf, flags)
    gp:session:user:<user_id>   → SET of session hashes for global logout
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from app.infrastructure.redis.client import RedisClient


@dataclass
class SessionRecord:
    user_id: str
    session_db_id: str
    csrf_token_hash: str
    absolute_expiry: int  # unix seconds
    idle_expiry: int
    created_at: int
    last_used_at: int
    ip_address: str | None = None
    user_agent: str | None = None
    device_label: str | None = None
    is_current: bool = False
    extra: dict = field(default_factory=dict)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionStore:
    _PREFIX = "gp:session"
    _USER_PREFIX = "gp:session:user"

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    def _key(self, token: str) -> str:
        return f"{self._PREFIX}:{_hash_token(token)}"

    def _user_key(self, user_id: uuid.UUID | str) -> str:
        return f"{self._USER_PREFIX}:{user_id}"

    async def save(self, token: str, record: SessionRecord) -> None:
        raw = asdict(record)
        await self._redis.set_json(self._key(token), raw, ttl=record.absolute_expiry)
        # Maintain user→session index for "logout all devices".
        await self._redis.client.sadd(self._user_key(record.user_id), _hash_token(token))
        await self._redis.client.expire(self._user_key(record.user_id), record.absolute_expiry)

    async def get(self, token: str) -> SessionRecord | None:
        raw = await self._redis.get_json(self._key(token))
        if raw is None:
            return None
        return SessionRecord(**raw)

    async def touch(self, token: str, *, absolute_expiry: int | None = None) -> None:
        key = self._key(token)
        record = await self.get(token)
        if record is None:
            return
        now = int(datetime.now(timezone.utc).timestamp())
        record.last_used_at = now
        if absolute_expiry:
            record.absolute_expiry = absolute_expiry
        await self._redis.set_json(key, asdict(record), ttl=record.absolute_expiry)

    async def delete(self, token: str) -> None:
        key = self._key(token)
        record = await self.get(token)
        if record is not None:
            await self._redis.client.srem(self._user_key(record.user_id), _hash_token(token))
        await self._redis.delete(key)

    async def revoke_all_for_user(self, user_id: uuid.UUID | str, except_token: str | None = None) -> int:
        """Log out every device for a user (except the current session if given)."""
        user_key = self._user_key(user_id)
        hashes = set(await self._redis.client.smembers(user_key))
        revoked = 0
        skip_hash = _hash_token(except_token) if except_token else None
        for h in hashes:
            if h == skip_hash:
                continue
            await self._redis.client.delete(f"{self._PREFIX}:{h}")
            revoked += 1
        await self._redis.delete(user_key)
        return revoked
