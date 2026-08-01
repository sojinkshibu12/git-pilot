"""Authentication endpoints: register, login, logout, me, verification, linking."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app.api.cookies import clear_session_cookie, set_session_cookie
from app.api.dependencies import (
    AuthenticatedContext,
    CsrfGuard,
    CurrentUser,
    get_authenticated_context,
)
from app.application.dependencies import Services, get_services
from app.core.config import get_settings
from app.core.exceptions import ConflictError, ValidationFailure
from app.core.logging import get_logger
from app.schemas import (
    AccountLinkRequest,
    GenericSuccess,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    ResendVerificationRequest,
    UserProfile,
)

logger = get_logger("api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/register",
    response_model=GenericSuccess,
    status_code=201,
    summary="Register with email + password",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    settings = get_settings()
    await services.rate_limiter.check(
        "auth", _client_ip(request) or "unknown", settings.RATE_LIMIT_AUTH_PER_MINUTE, 60
    )
    user = await services.auth.register(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request.state.request_id,
    )
    token = await services.auth.request_email_verification(user_id=user.id)
    await services.db.commit()
    return GenericSuccess(
        detail="Account created. Check your email to verify your address.",
        data={"verification_token": token} if get_settings().is_testing else None,
    )


@router.post("/login", response_model=UserProfile, summary="Log in with email + password")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    services: Annotated[Services, Depends(get_services)],
) -> UserProfile:
    settings = get_settings()
    await services.rate_limiter.check(
        "login", f"{_client_ip(request)}|{payload.email}", settings.RATE_LIMIT_LOGIN_PER_MINUTE, 60
    )
    user, session_token = await services.auth.login(
        email=payload.email,
        password=payload.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=request.state.request_id,
        remember_me=payload.remember_me,
    )
    set_session_cookie(response, session_token, settings, remember_me=payload.remember_me)
    await services.db.commit()
    return UserProfile.model_validate(user)


@router.post("/logout", response_model=GenericSuccess, summary="Log out current session")
async def logout(
    request: Request,
    response: Response,
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    settings = get_settings()
    raw = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if raw:
        await services.sessions.revoke_by_token(raw)
    clear_session_cookie(response, settings)
    await services.db.commit()
    return GenericSuccess(detail="Logged out.")


@router.post("/logout-all", response_model=GenericSuccess, summary="Log out every device")
async def logout_all(
    request: Request,
    response: Response,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    settings = get_settings()
    revoked = await services.sessions.revoke_all_for_user(
        context.user.id, request.cookies.get(settings.SESSION_COOKIE_NAME)
    )
    clear_session_cookie(response, settings)
    await services.db.commit()
    return GenericSuccess(detail=f"Logged out of {revoked} session(s).", data={"revoked": revoked})


@router.get("/me", response_model=UserProfile, summary="Current user profile")
async def me(
    current_user: CurrentUser, services: Annotated[Services, Depends(get_services)]
) -> UserProfile:
    return UserProfile.model_validate(current_user)


@router.post("/password/change", response_model=GenericSuccess, summary="Change password")
async def change_password(
    payload: PasswordChangeRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    await services.auth.change_password(
        user_id=context.user.id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        ip_address=context.session_record.ip_address,
        user_agent=context.session_record.user_agent,
    )
    await services.db.commit()
    return GenericSuccess(detail="Password updated.")


@router.post("/email/verify", response_model=GenericSuccess, summary="Verify email address")
async def verify_email(
    payload: dict[str, Any],
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    token = payload.get("token")
    if not token:
        raise ValidationFailure("Verification token is required.")
    ok = await services.auth.verify_email(token=token)
    await services.db.commit()
    if not ok:
        raise ValidationFailure("Invalid or expired verification token.")
    return GenericSuccess(detail="Email verified.")


@router.post("/email/resend", response_model=GenericSuccess, summary="Resend verification email")
async def resend_verification(
    payload: ResendVerificationRequest,
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    # In production this mails a link; in this build the token is returned for dev.
    from sqlalchemy import select

    from app.domain.models.identity import User

    user = await services.db.scalar(
        select(User).where(User.email == payload.email.lower(), User.deleted_at.is_(None))
    )
    if user is None:
        raise ConflictError("No account found for this email.")
    token = await services.auth.request_email_verification(user_id=user.id)
    await services.db.commit()
    return GenericSuccess(
        detail="Verification email sent.",
        data={"verification_token": token} if get_settings().is_testing else None,
    )


# --------------------------------------------------------------------------- #
# GitHub account linking
# --------------------------------------------------------------------------- #
@router.post("/link/github", response_model=GenericSuccess, summary="Link a GitHub account")
async def link_github(
    payload: AccountLinkRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> GenericSuccess:
    # The user performed the GitHub authorize step with a link state; the callback
    # already exchanged the code. This endpoint completes linking using the code
    # the frontend received in the callback (see oauth router).
    raise ValidationFailure("Use the dedicated OAuth callback with the link_state instead.")
