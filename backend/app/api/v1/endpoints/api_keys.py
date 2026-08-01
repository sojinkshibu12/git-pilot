"""API key management (machine-to-machine access)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, update

from app.api.dependencies import CsrfGuard, get_authenticated_context
from app.application.dependencies import Services, get_services
from app.core.security import generate_session_id
from app.domain.models.enums import AuditEventType
from app.domain.models.identity import APIKey
from app.schemas import APIKeyCreateRequest, APIKeyCreateResponse, APIKeySchema, GenericSuccess

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("/", response_model=list[APIKeySchema], summary="List API keys")
async def list_keys(
    context=Depends(get_authenticated_context),
    services: Annotated[Services, Depends(get_services)] = None,
) -> list[APIKeySchema]:
    keys = (
        await services.db.scalars(
            select(APIKey)
            .where(APIKey.user_id == context.user.id, APIKey.deleted_at.is_(None))
            .order_by(APIKey.created_at.desc())
        )
    ).all()
    return [APIKeySchema.model_validate(k) for k in keys]


@router.post("/", response_model=APIKeyCreateResponse, status_code=201, summary="Create API key")
async def create_key(
    payload: APIKeyCreateRequest,
    context=Depends(get_authenticated_context),
    _csrf: CsrfGuard = None,
    services: Annotated[Services, Depends(get_services)] = None,
) -> APIKeyCreateResponse:
    import hashlib

    from app.core.security import secrets

    raw = f"gp_{secrets.token_urlsafe(32)}"
    prefix = raw[:10]
    key = APIKey(
        user_id=context.user.id,
        name=payload.name,
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        key_prefix=prefix,
        scopes=" ".join(payload.scopes),
    )
    services.db.add(key)
    await services.db.flush()
    await services.audit.record(
        AuditEventType.API_KEY_CREATED,
        user_id=context.user.id,
        action="api_key.create",
        resource_id=str(key.id),
    )
    await services.db.commit()
    return APIKeyCreateResponse(id=key.id, name=key.name, key=raw)


@router.post("/{key_id}/revoke", response_model=GenericSuccess, summary="Revoke API key")
async def revoke_key(
    key_id: UUID,
    context=Depends(get_authenticated_context),
    _csrf: CsrfGuard = None,
    services: Annotated[Services, Depends(get_services)] = None,
) -> GenericSuccess:
    from datetime import datetime, timezone

    await services.db.execute(
        update(APIKey)
        .where(APIKey.id == key_id, APIKey.user_id == context.user.id)
        .values(deleted_at=datetime.now(timezone.utc))
    )
    await services.audit.record(
        AuditEventType.API_KEY_REVOKED,
        user_id=context.user.id,
        action="api_key.revoke",
        resource_id=str(key_id),
    )
    await services.db.commit()
    return GenericSuccess(detail="API key revoked.")
