"""Auth service — password registration/login, verification, linking.

Owns the user lifecycle orchestration. All security-sensitive transitions are
audited. Uses the OAuthService for GitHub-driven flows.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.audit_service import AuditService
from app.application.services.oauth_service import OAuthService
from app.application.services.session_service import SessionService
from app.application.services.token_service import TokenService
from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    ValidationFailure,
)
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.domain.models.enums import AuditEventType, UserStatus
from app.domain.models.identity import GitHubAccount, User
from app.infrastructure.redis.client import RedisClient

logger = get_logger("auth")

_VERIFY_PREFIX = "gp:email:verify:"
_RESET_PREFIX = "gp:email:reset:"


class AuthService:
    def __init__(
        self,
        *,
        settings: Settings,
        db: AsyncSession,
        redis: RedisClient,
        audit: AuditService,
        sessions: SessionService,
        oauth: OAuthService,
        tokens: TokenService,
    ) -> None:
        self._settings = settings
        self._db = db
        self._redis = redis
        self._audit = audit
        self._sessions = sessions
        self._oauth = oauth
        self._tokens = tokens

    # ------------------------------------------------------------------ #
    # Registration (email + password)
    # ------------------------------------------------------------------ #
    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None,
        ip_address: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> User:
        normalized = email.lower().strip()
        existing = await self._db.scalar(
            select(User).where(User.email == normalized, User.deleted_at.is_(None))
        )
        if existing is not None:
            await self._audit.record(
                AuditEventType.REGISTER,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                outcome="failure",
                action="register.conflict",
                metadata={"email": normalized},
            )
            raise ConflictError("An account with this email already exists.")

        user = User(
            email=normalized,
            email_verified=False,
            password_hash=hash_password(password, self._settings),
            display_name=display_name,
            status="pending_email",
        )
        self._db.add(user)
        await self._db.flush()

        await self._audit.record(
            AuditEventType.REGISTER,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            action="register.email",
        )
        return user

    async def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
        request_id: str | None,
        remember_me: bool,
    ) -> tuple[User, str]:
        """Validate credentials and create a session. Returns (user, session_token)."""
        normalized = email.lower().strip()
        user = await self._db.scalar(
            select(User).where(User.email == normalized, User.deleted_at.is_(None))
        )

        # Constant-ish failure path: still do a dummy verify to reduce timing signal.
        if user is None or not user.password_hash:
            verify_password(password, _dummy_hash())
            await self._audit.record(
                AuditEventType.LOGIN_FAILURE,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                outcome="failure",
                severity="warning",
                action="login.email",
                metadata={"reason": "no_account"},
            )
            raise AuthenticationError("Invalid email or password.")

        if user.status in {"disabled", "locked", "deleted"}:
            await self._audit.record(
                AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                outcome="failure",
                severity="warning",
                action="login.blocked",
                metadata={"status": user.status},
            )
            raise AuthenticationError("This account is not available.")

        if not verify_password(password, user.password_hash):
            await self._audit.record(
                AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                outcome="failure",
                severity="warning",
                action="login.email",
                metadata={"reason": "bad_password"},
            )
            raise AuthenticationError("Invalid email or password.")

        user.last_login_at = datetime.now(UTC)
        session_token, _db_session = await self._sessions.create_session(
            user_id=user.id,
            user_agent=user_agent,
            ip_address=ip_address,
            remember_me=remember_me,
        )
        await self._audit.record(
            AuditEventType.LOGIN_SUCCESS,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            action="login.email",
        )
        await self._db.flush()
        return user, session_token

    async def change_password(
        self,
        *,
        user_id: uuid.UUID,
        current_password: str,
        new_password: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        user = await self._db.get(User, user_id)
        if (
            user is None
            or not user.password_hash
            or not verify_password(current_password, user.password_hash)
        ):
            raise AuthenticationError("Current password is incorrect.")
        user.password_hash = hash_password(new_password, self._settings)
        await self._audit.record(
            AuditEventType.PASSWORD_CHANGED,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            action="password.change",
        )
        await self._db.flush()

    async def request_email_verification(self, *, user_id: uuid.UUID) -> str:
        token = secrets.token_urlsafe(32)
        ttl = self._settings.EMAIL_VERIFICATION_TOKEN_TTL
        await self._redis.set_json(f"{_VERIFY_PREFIX}{token}", {"user_id": str(user_id)}, ttl=ttl)
        return token

    async def verify_email(self, *, token: str, user_id: uuid.UUID | None = None) -> bool:
        key = f"{_VERIFY_PREFIX}{token}"
        payload = await self._redis.get_json(key)
        if not payload:
            return False
        stored_user_id = payload.get("user_id")
        if user_id is not None and stored_user_id != str(user_id):
            return False
        if stored_user_id is None:
            return False
        user = await self._db.get(User, uuid.UUID(stored_user_id))
        if user:
            user.email_verified = True
            if user.status == UserStatus.PENDING_EMAIL.value:
                user.status = UserStatus.ACTIVE.value
            await self._db.flush()
        await self._redis.delete(key)
        return True

    # ------------------------------------------------------------------ #
    # GitHub linking
    # ------------------------------------------------------------------ #
    async def begin_github_link(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[str, str, str]:
        """Start linking a GitHub identity to an existing (password) user."""
        return await self._oauth.begin(
            session_id=session_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            link_to_user_id=user_id,
        )

    async def complete_github_link(
        self,
        *,
        user_id: uuid.UUID,
        link_token: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> GitHubAccount:
        return await self._oauth.complete_link(
            link_token=link_token,
            password=password,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

    async def unlink_github(self, *, user_id: uuid.UUID, github_account_id: uuid.UUID) -> None:
        account = await self._db.scalar(
            select(GitHubAccount).where(
                GitHubAccount.id == github_account_id,
                GitHubAccount.user_id == user_id,
                GitHubAccount.deleted_at.is_(None),
            )
        )
        if account is None:
            raise ValidationFailure("GitHub account not linked to this user.")
        await self._tokens.revoke_all_for_user(user_id)
        await self._db.delete(account)
        await self._db.flush()
        await self._audit.record(
            AuditEventType.ACCOUNT_UNLINKED,
            user_id=user_id,
            github_id=account.github_id,
            action="account.unlink.github",
        )


_DUMMY_HASH: str | None = None


def get_settings() -> Settings:
    from app.core.config import get_settings as _get_settings

    return _get_settings()


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-password-placeholder!", get_settings())
    return _DUMMY_HASH
