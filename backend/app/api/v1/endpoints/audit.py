"""Audit log query endpoints (self-service security review)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.dependencies import AuthenticatedContext, get_authenticated_context
from app.application.dependencies import Services, get_services
from app.domain.models.identity import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", summary="List audit events for the current user")
async def list_audit_events(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    limit: int = 50,
) -> dict[str, Any]:
    rows = (
        await services.db.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == context.user.id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
    ).all()
    return {
        "events": [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "created_at": r.created_at.isoformat(),
                "severity": r.severity,
                "outcome": r.outcome,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "action": r.action,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "metadata": r.metadata_,
            }
            for r in rows
        ]
    }
