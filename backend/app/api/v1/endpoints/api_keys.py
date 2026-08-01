"""API key management (machine-to-machine access)."""

from __future__ import annotations

from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, update

from app.api.dependencies import AuthenticatedContext, CsrfGuard, get_authenticated_context
from app.application.dependencies import Services, get_services
from app.domain.models.enums import AuditEventType
from app.domain.models.identity import APIKey
from app.schemas import APIKeyCreateRequest, APIKeyCreateResponse, APIKeySchema, GenericSuccess

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("/", response_model=list[APIKeySchema], summary="List API keys")
async def list_keys(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> list[APIKeySchema]:
    keys = (
        await services.db.scalars(
            select(APIKey)
            .where(APIKey.user_id == context.user.id, APIKey.deleted_at.is_(None))
            .order_by(APIKey.created_at.desc())
        )
    ).all()
    result = []
    for k in keys:
        item = APIKeySchema.model_construct(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes.split(),
            last_used_at=k.last_used_at,
            expires_at=k.expires_at,
            created_at=k.created_at,
        )
        result.append(item)
    return result


@router.post("/", response_model=APIKeyCreateResponse, status_code=201, summary="Create API key")
async def create_key(
    payload: APIKeyCreateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> APIKeyCreateResponse:
    import hashlib
    import secrets

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
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    from datetime import datetime

    await services.db.execute(
        update(APIKey)
        .where(APIKey.id == key_id, APIKey.user_id == context.user.id)
        .values(deleted_at=datetime.now(UTC))
    )
    await services.audit.record(
        AuditEventType.API_KEY_REVOKED,
        user_id=context.user.id,
        action="api_key.revoke",
        resource_id=str(key_id),
    )
    await services.db.commit()
    return GenericSuccess(detail="API key revoked.")
