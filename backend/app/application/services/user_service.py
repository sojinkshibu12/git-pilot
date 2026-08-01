"""User service — profile, preferences, connected accounts, security overview."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.audit_service import AuditService
from app.application.services.session_service import SessionService
from app.application.services.token_service import TokenService
from app.core.exceptions import NotFoundError
from app.domain.models.enums import AuthProvider
from app.domain.models.identity import GitHubAccount, User, UserPreferences
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.github.exceptions import GitHubClientError


class UserService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        audit: AuditService,
        sessions: SessionService,
        tokens: TokenService,
        github: GitHubAPIClient,
    ) -> None:
        self._db = db
        self._audit = audit
        self._sessions = sessions
        self._tokens = tokens
        self._github = github

    async def get_profile(self, user_id: uuid.UUID) -> User:
        user = await self._db.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def update_profile(self, user_id: uuid.UUID, **fields: Any) -> User:
        user = await self._db.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found.")
        for key in ("display_name", "locale", "avatar_url"):
            if key in fields:
                setattr(user, key, fields[key])
        await self._db.flush()
        return user

    async def get_preferences(self, user_id: uuid.UUID) -> UserPreferences:
        prefs = await self._db.scalar(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        if prefs is None:
            prefs = UserPreferences(user_id=user_id)
            self._db.add(prefs)
            await self._db.flush()
        return prefs

    async def update_preferences(self, user_id: uuid.UUID, **fields: Any) -> UserPreferences:
        prefs = await self.get_preferences(user_id)
        for key, value in fields.items():
            setattr(prefs, key, value)
        await self._db.flush()
        return prefs

    async def list_connected_accounts(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        accounts = (
            await self._db.scalars(
                select(GitHubAccount)
                .where(GitHubAccount.user_id == user_id, GitHubAccount.deleted_at.is_(None))
                .order_by(GitHubAccount.created_at)
            )
        ).all()

        github = accounts[0] if accounts else None
        result: list[dict[str, Any]] = []
        for provider in (
            AuthProvider.GITHUB,
            AuthProvider.GOOGLE,
            AuthProvider.MICROSOFT,
            AuthProvider.GITLAB,
        ):
            is_github = provider == AuthProvider.GITHUB
            connected = is_github and github is not None
            if connected and github is not None:
                account: dict[str, Any] = {
                    "provider": provider,
                    "connected": True,
                    "primary": True,
                    "github_id": github.github_id,
                    "login": github.login,
                    "avatar_url": github.avatar_url,
                    "email": github.email,
                    "email_verified": github.email_verified,
                    "display_name": github.display_name,
                }
            else:
                account = {
                    "provider": provider,
                    "connected": False,
                    "primary": False,
                    "github_id": None,
                    "login": None,
                    "avatar_url": None,
                    "email": None,
                    "email_verified": False,
                    "display_name": None,
                }
            result.append(account)
        return result

    async def security_overview(self, user_id: uuid.UUID) -> dict[str, Any]:
        user = await self.get_profile(user_id)
        active = await self._sessions.count_active(user_id)
        accounts = await self.list_connected_accounts(user_id)
        return {
            "has_password": bool(user.password_hash),
            "mfa_enabled": user.mfa_enabled,
            "email_verified": user.email_verified,
            "connected_accounts": accounts,
            "active_sessions_count": active,
        }

    async def github_profile_from_api(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Return live GitHub profile for the user's primary account (cached)."""
        try:
            token = await self._tokens.access_token_for_user(user_id)
        except Exception:  # noqa: BLE001
            return None
        try:
            gh_user = await self._github.get_user(token)
        except GitHubClientError:
            return None
        return gh_user.model_dump()
