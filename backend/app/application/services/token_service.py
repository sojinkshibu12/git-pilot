"""Token service — encrypt/decrypt/store GitHub credentials.

Access and refresh tokens are encrypted with AES-256-GCM via the TokenVault
before touching the database. The plaintext token exists in memory only for the
lifetime of a single request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TokenInvalidError
from app.core.logging import get_logger
from app.core.security import TokenVault
from app.domain.models.github import GitHubCredential
from app.domain.models.identity import GitHubAccount

logger = get_logger("tokens")


@dataclass
class DecryptedCredential:
    github_account_id: uuid.UUID
    github_id: int
    access_token: str
    refresh_token: str | None = None
    scopes: list[str] | None = None
    expires_at: datetime | None = None


class TokenService:
    def __init__(self, session: AsyncSession, vault: TokenVault) -> None:
        self._session = session
        self._vault = vault

    async def store_credential(
        self,
        *,
        github_account_id: uuid.UUID,
        user_id: uuid.UUID,
        github_id: int,
        access_token: str,
        refresh_token: str | None = None,
        scopes: str = "",
        expires_at: datetime | None = None,
        refresh_expires_at: datetime | None = None,
    ) -> GitHubCredential:
        # Deactivate any existing active row (token rotation).
        await self._session.execute(
            update(GitHubCredential)
            .where(
                GitHubCredential.github_account_id == github_account_id,
                GitHubCredential.is_active.is_(True),
            )
            .values(is_active=False)
        )

        cred = GitHubCredential(
            github_account_id=github_account_id,
            user_id=user_id,
            github_id=github_id,
            is_active=True,
            access_token_encrypted=self._vault.encrypt(access_token),
            refresh_token_encrypted=self._vault.encrypt(refresh_token) if refresh_token else None,
            scopes=scopes,
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at,
            encryption_metadata={"algorithm": "aes-256-gcm", "key_id": "v1"},
            token_version=1,
        )
        self._session.add(cred)
        await self._session.flush()
        return cred

    async def get_active_credential(self, github_account_id: uuid.UUID) -> GitHubCredential | None:
        return cast(
            GitHubCredential | None,
            await self._session.scalar(
                select(GitHubCredential).where(
                    GitHubCredential.github_account_id == github_account_id,
                    GitHubCredential.is_active.is_(True),
                    GitHubCredential.deleted_at.is_(None),
                )
            ),
        )

    async def decrypt_credential(self, github_account_id: uuid.UUID) -> DecryptedCredential:
        cred = await self.get_active_credential(github_account_id)
        if cred is None:
            raise TokenInvalidError("No GitHub credential stored for this account.")

        # Enforce refresh expiry / access expiry.
        now = datetime.now(UTC)
        expires_at = cred.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at and expires_at < now:
            if cred.refresh_token_encrypted:
                raise TokenInvalidError("GitHub access token expired; refresh required.")
            raise TokenInvalidError("GitHub access token expired.")
        refresh_expires_at = cred.refresh_expires_at
        if refresh_expires_at is not None and refresh_expires_at.tzinfo is None:
            refresh_expires_at = refresh_expires_at.replace(tzinfo=UTC)
        if refresh_expires_at and refresh_expires_at < now:
            raise TokenInvalidError("GitHub refresh token expired; re-authenticate.")

        try:
            access = self._vault.decrypt(cred.access_token_encrypted)
            refresh = (
                self._vault.decrypt(cred.refresh_token_encrypted)
                if cred.refresh_token_encrypted
                else None
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("token_decryption_failed", account_id=str(github_account_id))
            raise TokenInvalidError("Failed to decrypt stored credential.") from exc

        return DecryptedCredential(
            github_account_id=cred.github_account_id,
            github_id=cred.github_id,
            access_token=access,
            refresh_token=refresh,
            scopes=[s for s in cred.scopes.split() if s],
            expires_at=cred.expires_at,
        )

    async def access_token_for_user(self, user_id: uuid.UUID) -> str:
        """Primary account access token for a user (for API surface)."""
        account = await self._session.scalar(
            select(GitHubAccount)
            .where(GitHubAccount.user_id == user_id, GitHubAccount.deleted_at.is_(None))
            .limit(1)
        )
        if account is None:
            raise TokenInvalidError("No linked GitHub account.")
        cred = await self.decrypt_credential(account.id)
        return cred.access_token

    async def github_login_for_user(self, user_id: uuid.UUID) -> str | None:
        """GitHub login of the user's primary linked account (for commit filtering)."""
        account = await self._session.scalar(
            select(GitHubAccount)
            .where(GitHubAccount.user_id == user_id, GitHubAccount.deleted_at.is_(None))
            .limit(1)
        )
        return account.login if account is not None else None

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(GitHubCredential)
            .where(GitHubCredential.user_id == user_id, GitHubCredential.is_active.is_(True))
            .values(is_active=False)
        )
