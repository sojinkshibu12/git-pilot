"""Authentication dependencies for protected routes.

`get_current_user`:
- Reads the HttpOnly session cookie
- Validates it against the Redis session store + DB record
- Enforces absolute + idle timeouts
- Returns the authenticated `User` (or raises 401 / 403)

`get_csrf_guard`:
- Verifies the `X-CSRF-Token` header against the session's CSRF token for
  mutating requests (double-submit pattern with server-side binding).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from app.application.dependencies import Services, get_services
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, InvalidSessionError, SessionExpiredError
from app.domain.models.identity import User
from app.infrastructure.security.session_store import SessionRecord


@dataclass
class AuthenticatedContext:
    user: User
    session_record: SessionRecord
    session_id: uuid.UUID
    csrf_token_hash: str


async def _resolve_session(request: Request, services: Services) -> tuple[SessionRecord, User] | None:
    settings = get_settings()
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw_token:
        return None

    record = await services.sessions.validate(raw_token)
    if record is None:
        return None

    user = await services.db.get(User, uuid.UUID(record.user_id))
    if user is None or user.deleted_at is not None:
        raise InvalidSessionError("Session references a deleted user.")
    if user.status in {"disabled", "locked"}:
        raise InvalidSessionError("Account is not available.")
    return record, user


async def get_current_user(
    request: Request,
    services: Annotated[Services, Depends(get_services)],
) -> User:
    resolved = await _resolve_session(request, services)
    if resolved is None:
        if not request.cookies.get(get_settings().SESSION_COOKIE_NAME):
            raise AuthenticationError("Sign in to continue.")
        raise SessionExpiredError("Your session has expired. Please sign in again.")
    record, user = resolved
    return user


async def get_authenticated_context(
    request: Request,
    services: Annotated[Services, Depends(get_services)],
) -> AuthenticatedContext:
    resolved = await _resolve_session(request, services)
    if resolved is None:
        if not request.cookies.get(get_settings().SESSION_COOKIE_NAME):
            raise AuthenticationError("Sign in to continue.")
        raise SessionExpiredError("Your session has expired. Please sign in again.")
    record, user = resolved

    # Session rotation on timer (defends against fixation/leakage).
    # A middleware applies `request.state.new_session_token` to the response.
    import time as _time

    settings = get_settings()
    rotated_at = record.extra.get("rotated_at") or record.last_used_at
    if _time.time() - int(rotated_at) >= settings.SESSION_ROTATION_SECONDS:
        raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME) or ""
        new_token = await services.sessions.rotate(raw_token)
        if new_token:
            request.state.new_session_token = new_token
            record.extra["rotated_at"] = int(_time.time())
            await services.sessions.touch(new_token)

    return AuthenticatedContext(
        user=user,
        session_record=record,
        session_id=uuid.UUID(record.session_db_id),
        csrf_token_hash=record.csrf_token_hash,
    )


async def get_csrf_guard(
    request: Request,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> None:
    from app.core.security import constant_time_eq

    if not x_csrf_token:
        raise AuthenticationError("CSRF token missing.")
    if not constant_time_eq(x_csrf_token, context.csrf_token_hash):
        raise AuthenticationError("CSRF validation failed.")


CurrentUser = Annotated[User, Depends(get_current_user)]
Authenticated = Annotated[AuthenticatedContext, Depends(get_authenticated_context)]
CsrfGuard = Annotated[None, Depends(get_csrf_guard)]
