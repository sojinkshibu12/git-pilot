"""Cookie helpers for session management.

The session cookie is HttpOnly, Secure (in prod), SameSite=Lax/Strict, and only
carries an opaque token. CSRF is protected via a separate header token bound to
the session.
"""
from __future__ import annotations

from fastapi import Response

from app.core.config import Settings


def set_session_cookie(response: Response, token: str, settings: Settings, *, remember_me: bool = False) -> None:
    max_age = settings.SESSION_TTL_SECONDS * (14 if remember_me else 1)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=max_age,
        path="/",
        domain=settings.SESSION_COOKIE_DOMAIN or None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE.value,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        domain=settings.SESSION_COOKIE_DOMAIN or None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE.value,
    )
