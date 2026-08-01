"""Active session management endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import AuthenticatedContext, CsrfGuard, get_authenticated_context
from app.application.dependencies import Services, get_services
from app.schemas import GenericSuccess, LogoutAllResponse, SessionInfo, SessionListResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/", response_model=SessionListResponse, summary="List active sessions")
async def list_sessions(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> SessionListResponse:
    sessions = await services.sessions.list_active(context.user.id, context.session_id)
    return SessionListResponse(sessions=[SessionInfo.model_validate(s) for s in sessions])


@router.post("/{session_id}/revoke", response_model=GenericSuccess, summary="Revoke a session")
async def revoke_session(
    session_id: UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    await services.sessions.revoke(session_id, context.user.id, reason="user_revoked")
    await services.db.commit()
    return GenericSuccess(detail="Session revoked.")


@router.post("/revoke-all", response_model=LogoutAllResponse, summary="Revoke all other sessions")
async def revoke_all(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> LogoutAllResponse:
    # We keep the current session: revoke only the others.
    other_sessions = await services.sessions.list_active(context.user.id, context.session_id)
    for s in other_sessions:
        if not s.is_current:
            await services.sessions.revoke(s.id, context.user.id, reason="revoke_all")
    await services.db.commit()
    return LogoutAllResponse(revoked=len([s for s in other_sessions if not s.is_current]))


@router.post(
    "/csrf", response_model=GenericSuccess, summary="Fetch a CSRF token bound to this session"
)
async def csrf_token(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    """Return the CSRF token for the current session (double-submit binding).

    The frontend must submit it in the `X-CSRF-Token` header for mutating calls.
    """
    return GenericSuccess(
        detail="CSRF token issued.",
        data={"csrf_token": context.csrf_token_hash},
    )
