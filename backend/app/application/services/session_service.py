"""Session service — create, validate, rotate, and revoke sessions.

Two stores:
- Redis: fast session payload (opaque cookie token → SessionRecord)
- PostgreSQL: durable authoritative record (Session row)

Sessions are rotated on a timer, have absolute + idle TTLs, and are bound to a
user-agent/IP fingerprint for anomaly detection.
"""

from __future__ import annotations

import hashlib
import ipaddress
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.audit_service import AuditService
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import generate_session_id
from app.domain.models.enums import AuditEventType, SessionStatus
from app.domain.models.identity import Session
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.security.session_store import SessionRecord, SessionStore

logger = get_logger("sessions")


class SessionService:
    def __init__(
        self,
        session: AsyncSession,
        redis: RedisClient,
        settings: Settings,
        audit: AuditService | None = None,
    ) -> None:
        self._db = session
        self._redis = redis
        self._settings = settings
        self._store = SessionStore(redis)
        self._audit = audit

    @staticmethod
    def _hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _safe_ip(client_ip: str) -> str:
        """Store network-prefixed IPs in sessions/audit to avoid PII leaks."""
        try:
            ip = ipaddress.ip_address(client_ip)
        except ValueError:
            return client_ip[:45]
        if isinstance(ip, ipaddress.IPv6Address):
            return str(ip)
        return str(ip)  # IPv4 kept in full for audit; truncate if required by policy

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        user_agent: str | None,
        ip_address: str | None,
        remember_me: bool = False,
        device_label: str | None = None,
    ) -> tuple[str, Session]:
        now = datetime.now(UTC)
        raw_token = generate_session_id()
        token_hash = self._hash(raw_token)
        csrf_token = generate_session_id()
        csrf_hash = self._hash(csrf_token)

        absolute_ttl = self._settings.SESSION_TTL_SECONDS * (14 if remember_me else 1)
        expires_at = now + timedelta(seconds=absolute_ttl)

        db_session = Session(
            user_id=user_id,
            session_token_hash=token_hash,
            csrf_token_hash=csrf_hash,
            status=SessionStatus.ACTIVE,
            expires_at=expires_at,
            last_used_at=now,
            rotated_at=now,
            ip_address=self._safe_ip(ip_address) if ip_address else None,
            user_agent=(user_agent or "")[:512],
            device_label=device_label,
            is_current=True,
        )
        self._db.add(db_session)
        await self._db.flush()

        record = SessionRecord(
            user_id=str(user_id),
            session_db_id=str(db_session.id),
            csrf_token_hash=csrf_hash,
            absolute_expiry=int(expires_at.timestamp()),
            idle_expiry=int(
                (now + timedelta(seconds=self._settings.SESSION_IDLE_TIMEOUT_SECONDS)).timestamp()
            ),
            created_at=int(now.timestamp()),
            last_used_at=int(now.timestamp()),
            ip_address=self._safe_ip(ip_address) if ip_address else None,
            user_agent=(user_agent or "")[:512],
            device_label=device_label,
            is_current=True,
        )
        await self._store.save(raw_token, record)

        if self._audit is not None:
            await self._audit.record(
                AuditEventType.SESSION_CREATED,
                user_id=user_id,
                session_id=db_session.id,
                ip_address=ip_address,
                user_agent=user_agent,
                action="session.create",
                metadata={"remember_me": remember_me, "device_label": device_label},
            )

        return raw_token, db_session

    async def validate(self, raw_token: str) -> SessionRecord | None:
        """Validate + touch a session. Returns None if invalid/expired."""
        if not raw_token:
            return None
        record = await self._store.get(raw_token)
        if record is None:
            return None
        now = datetime.now(UTC).timestamp()
        # Absolute expiry
        if now > record.absolute_expiry:
            await self._store.delete(raw_token)
            await self._expire_db_session(uuid.UUID(record.session_db_id))
            return None
        # Idle timeout
        if now > record.idle_expiry:
            await self._store.delete(raw_token)
            await self._expire_db_session(uuid.UUID(record.session_db_id), reason="idle_timeout")
            return None
        await self._store.touch(raw_token)
        await self._touch_db_session(uuid.UUID(record.session_db_id))
        return record

    async def _touch_db_session(self, session_db_id: uuid.UUID) -> None:
        await self._db.execute(
            update(Session)
            .where(Session.id == session_db_id)
            .values(last_used_at=datetime.now(UTC))
        )
        await self._db.flush()

    async def _expire_db_session(self, session_db_id: uuid.UUID, reason: str = "expired") -> None:
        await self._db.execute(
            update(Session)
            .where(Session.id == session_db_id, Session.status == SessionStatus.ACTIVE)
            .values(status=SessionStatus.EXPIRED, revoked_reason=reason)
        )
        await self._db.flush()
        if self._audit is not None:
            await self._audit.record(
                AuditEventType.SESSION_EXPIRED,
                session_id=session_db_id,
                action="session.expire",
                metadata={"reason": reason},
            )

    async def revoke(
        self, session_db_id: uuid.UUID, user_id: uuid.UUID, *, reason: str = "revoked"
    ) -> None:
        await self._db.execute(
            update(Session)
            .where(Session.id == session_db_id, Session.user_id == user_id)
            .values(status=SessionStatus.REVOKED, revoked_reason=reason)
        )
        await self._db.flush()

    async def revoke_by_token(self, raw_token: str) -> None:
        record = await self._store.get(raw_token)
        if record:
            await self._store.delete(raw_token)
            await self.revoke(
                uuid.UUID(record.session_db_id), uuid.UUID(record.user_id), reason="logout"
            )
        await self._db.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID, except_token: str | None = None) -> int:
        n = await self._store.revoke_all_for_user(user_id, except_token)
        await self._db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.status == SessionStatus.ACTIVE)
            .values(status=SessionStatus.TERMINATED, revoked_reason="logout_all")
        )
        await self._db.flush()
        if self._audit is not None:
            await self._audit.record(
                AuditEventType.SESSION_REVOKED,
                user_id=user_id,
                action="session.revoke_all",
                metadata={"revoked": n},
            )
        return n

    async def rotate(self, raw_token: str) -> str | None:
        """Rotate the session token (session fixation defense). Returns new token."""
        record = await self._store.get(raw_token)
        if record is None:
            return None
        new_token = generate_session_id()
        record.extra["prev_token_hash"] = self._hash(raw_token)
        await self._store.save(new_token, record)
        await self._store.delete(raw_token)

        now = datetime.now(UTC)
        await self._db.execute(
            update(Session)
            .where(Session.id == uuid.UUID(record.session_db_id))
            .values(
                session_token_hash=self._hash(new_token),
                rotated_at=now,
            )
        )
        await self._db.flush()
        return new_token

    async def touch(self, raw_token: str) -> None:
        """Update the last-used timestamp for a session token."""
        await self._store.touch(raw_token)

    async def list_active(
        self, user_id: uuid.UUID, current_session_id: uuid.UUID | None = None
    ) -> list[Session]:
        stmt = (
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.status == SessionStatus.ACTIVE,
                Session.deleted_at.is_(None),
            )
            .order_by(Session.created_at.desc())
        )
        sessions = (await self._db.scalars(stmt)).all()
        for s in sessions:
            s.is_current = s.id == current_session_id
        return list(sessions)

    async def count_active(self, user_id: uuid.UUID) -> int:
        return (
            await self._db.scalar(
                select(Session.id)
                .where(
                    Session.user_id == user_id,
                    Session.status == SessionStatus.ACTIVE,
                    Session.deleted_at.is_(None),
                )
                .limit(1)
            )
            is not None
        )

    async def has_active_sessions(self, user_id: uuid.UUID) -> bool:
        return bool(
            await self._db.scalar(
                select(Session.id)
                .where(Session.user_id == user_id, Session.status == SessionStatus.ACTIVE)
                .limit(1)
            )
        )
