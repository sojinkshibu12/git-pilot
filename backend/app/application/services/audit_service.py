"""Audit service — append-only, tamper-evident-ish event log.

Every security-relevant event is persisted to `audit_logs` AND emitted through
structured logging with correlation context. In production, wire the event
stream to your SIEM via the log sink.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.enums import AuditEventType
from app.domain.models.identity import AuditLog

logger = get_logger("audit")


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        event_type: AuditEventType,
        *,
        user_id: uuid.UUID | None = None,
        github_id: int | None = None,
        session_id: uuid.UUID | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        severity: str = "info",
        outcome: str = "success",
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLog(
            event_type=event_type.value if isinstance(event_type, AuditEventType) else event_type,
            user_id=user_id,
            github_id=github_id,
            session_id=session_id,
            request_id=request_id,
            correlation_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=severity,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            metadata_=metadata or {},
        )
        self._session.add(entry)

        # Structured log line with same fields (SIEM-friendly).
        log = logger.bind(
            event=event_type.value if isinstance(event_type, AuditEventType) else event_type,
            severity=severity,
            outcome=outcome,
            user_id=str(user_id) if user_id else None,
            github_id=github_id,
            session_id=str(session_id) if session_id else None,
            request_id=request_id,
            correlation_id=correlation_id,
            ip=ip_address,
        )
        if severity in {"critical", "error", "warning"}:
            log.warning("audit_event", **metadata or {})
        else:
            log.info("audit_event", **metadata or {})

    async def flush(self) -> None:
        await self._session.flush()
