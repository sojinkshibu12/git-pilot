"""OAuth endpoints for GitHub Authorization Code + PKCE flow.

- `GET  /oauth/github/begin`        → build authorize URL (state + PKCE)
- `GET  /oauth/github/callback`     → GitHub redirect target (validates state,
                                       exchanges code, creates/logs in/links)
- `POST /oauth/link/complete`       → finish GitHub→Password account linking

The callback sets the session cookie directly. Errors are surfaced with stable
codes so the frontend can render dedicated screens (expired, cancelled,
rate-limited, etc.).
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from app.api.cookies import clear_session_cookie, set_session_cookie
from app.application.dependencies import Services, get_services
from app.core.config import get_settings
from app.core.exceptions import (
    AccountLinkingRequiredError,
    OAuthCancelledError,
    OAuthStateExpiredError,
    OAuthStateMismatchError,
)
from app.schemas import GenericSuccess, OAuthAuthorizeResponse

router = APIRouter(prefix="/oauth", tags=["oauth"])

_FRONTEND_REDIRECT_BASE = "http://localhost:3000/auth/callback"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get(
    "/github/begin",
    response_model=OAuthAuthorizeResponse,
    summary="Start GitHub OAuth (Authorization Code + PKCE)",
)
async def oauth_begin(
    request: Request,
    services: Annotated[Services, Depends(get_services)],
    link_to: UUID | None = None,
) -> OAuthAuthorizeResponse:
    settings = get_settings()
    await services.rate_limiter.check(
        "oauth_begin", _client_ip(request) or "unknown", settings.RATE_LIMIT_AUTH_PER_MINUTE, 60
    )
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_id = None
    user_id = None
    if raw_token:
        record = await services.sessions.validate(raw_token)
        if record:
            session_id = UUID(record.session_db_id)
            user_id = UUID(record.user_id)

    url, state, method = await services.oauth.begin(
        session_id=session_id,
        user_id=user_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        link_to_user_id=link_to,
    )
    await services.db.commit()
    return OAuthAuthorizeResponse(authorize_url=url, state=state, pkce_method=method)


@router.get(
    "/github/callback",
    summary="GitHub OAuth callback (token exchange happens backend-side)",
    response_class=RedirectResponse,
    include_in_schema=False,
)
async def oauth_callback(
    request: Request,
    services: Annotated[Services, Depends(get_services)],
    state: str = "",
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    response = RedirectResponse(url="/")

    try:
        user, account, access_token = await services.oauth.handle_callback(
            state=state,
            code=code,
            error=error,
            error_description=error_description,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=request.state.request_id,
        )
        # Rotate: create a fresh session (post-auth session fixation defense).
        session_token, _db_session = await services.sessions.create_session(
            user_id=user.id,
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
            remember_me=False,
            device_label="GitHub Sign-in",
        )
        await services.db.commit()
        response = RedirectResponse(url=f"/auth/callback?provider=github&status=success")
        response.status_code = 303
        set_session_cookie(response, session_token, settings)
        return response
    except AccountLinkingRequiredError as exc:
        await services.db.rollback()
        details = exc.details.get("details") or {}
        return _redirect_with_error(
            response,
            status="link_required",
            link_token=str(details.get("link_token", "")),
            email=str(details.get("email", "")),
            github_login=str(details.get("github_login", "")),
        )
    except OAuthCancelledError:
        await services.db.rollback()
        return _redirect_with_error(response, status="cancelled")
    except OAuthStateExpiredError:
        await services.db.rollback()
        return _redirect_with_error(response, status="state_expired")
    except OAuthStateMismatchError:
        await services.db.rollback()
        return _redirect_with_error(response, status="state_mismatch")
    except Exception as exc:  # noqa: BLE001
        await services.db.rollback()
        clear_session_cookie(response, settings)
        from app.core.logging import get_logger

        get_logger("oauth.callback").exception(
            "oauth_callback_unexpected_error",
            request_id=request.state.request_id,
            error=str(exc),
        )
        return _redirect_with_error(response, status="error")


def _redirect_with_error(response: RedirectResponse, status: str, **extra: str) -> RedirectResponse:
    from urllib.parse import urlencode

    qs = urlencode({"provider": "github", "status": status, **extra})
    response.headers["Location"] = f"{_FRONTEND_REDIRECT_BASE}?{qs}"
    response.status_code = 303
    return response


@router.post(
    "/link/complete",
    response_model=GenericSuccess,
    summary="Complete GitHub→Password account linking",
)
async def complete_link(
    payload: dict,
    request: Request,
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    link_token = payload.get("link_token")
    password = payload.get("password")
    if not link_token or not password:
        from app.core.exceptions import ValidationFailure

        raise ValidationFailure("link_token and password are required.")
    from app.domain.models.identity import User
    from sqlalchemy import select

    user = await services.db.scalar(
        select(User).where(User.email == str(payload.get("email", "")).lower(), User.deleted_at.is_(None))
    )
    if user is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Existing account not found.")

    account = await services.auth.complete_github_link(
        user_id=user.id,
        link_token=link_token,
        password=password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request.state.request_id,
    )
    await services.db.commit()
    return GenericSuccess(
        detail="GitHub account linked.",
        data={"github_id": account.github_id, "login": account.login},
    )
