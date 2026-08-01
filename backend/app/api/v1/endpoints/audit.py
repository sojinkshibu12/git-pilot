"""Audit log query endpoints (self-service security review)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.dependencies import get_authenticated_context
from app.application.dependencies import Services, get_services
from app.domain.models.identity import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", summary="List audit events for the current user")
async def list_audit_events(
    context=Depends(get_authenticated_context),
    services: Annotated[Services, Depends(get_services)] = None,
    limit: int = 50,
):
    rows = (
        await services.db.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == context.user.id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
    ).all()
    return {"events": [r.dict() for r in rows]}
