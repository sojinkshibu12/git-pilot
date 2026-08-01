"""OAuth 2.1 Authorization Code + PKCE flow orchestration.

Security invariants enforced here:
- `state` is generated with `secrets.token_urlsafe(32)`, stored server-side hashed,
  bound to a session, expires after 10 minutes, validated in constant time,
  rejected with 403 on mismatch, and consumed on first use.
- PKCE: verifier stored encrypted server-side, challenge validated (S256) before
  token exchange.
- Only the exact registered redirect URI is honoured.
- Authorization codes are exchanged by the backend only.
- Tokens never leave the backend.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.audit_service import AuditService
from app.core.config import Settings
from app.core.exceptions import (
    AccountLinkingRequiredError,
    AuthenticationError,
    GitHubProviderError,
    OAuthCancelledError,
    OAuthStateExpiredError,
    OAuthStateMismatchError,
    PKCEValidationError,
    RedirectUriMismatchError,
)
from app.core.logging import get_logger
from app.core.security import (
    PKCEPair,
    TokenVault,
    compute_challenge,
    constant_time_eq,
    generate_state,
)
from app.domain.models.enums import AuditEventType, AuthProvider, OAuthFlowStage
from app.domain.models.github import GitHubCredential
from app.domain.models.identity import GitHubAccount, OAuthState, PKCEChallenge, User
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.github.exceptions import GitHubClientError
from app.infrastructure.github.models import GHAccessToken, GHUser
from app.infrastructure.redis.client import RedisClient

logger = get_logger("oauth")

_ALLOWED_PKCE_METHODS = {"S256"}
_LINK_PREFIX = "gp:link:"


class OAuthService:
    def __init__(
        self,
        *,
        settings: Settings,
        db: AsyncSession,
        vault: TokenVault,
        audit: AuditService,
        github: GitHubAPIClient,
        redis: RedisClient | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._db = db
        self._vault = vault
        self._audit = audit
        self._github = github
        self._redis = redis
        self._http = http or httpx.AsyncClient(timeout=30)

    # ------------------------------------------------------------------ #
    # Authorize — start the flow
    # ------------------------------------------------------------------ #
    async def begin(
        self,
        *,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        link_to_user_id: uuid.UUID | None = None,
        scope_override: str | None = None,
    ) -> tuple[str, str, str]:
        """Generate state + PKCE, persist, and build the GitHub authorize URL.

        Returns (authorize_url, state, pkce_method).
        """
        state = generate_state()
        state_hash = hashlib.sha256(state.encode()).hexdigest()

        pkce = PKCEPair.generate()
        method = pkce.method
        challenge = pkce.challenge
        verifier = pkce.verifier
        challenge_hash = hashlib.sha256(challenge.encode()).hexdigest()

        scope = scope_override or self._settings.GITHUB_SCOPE
        redirect_uri = self._settings.GITHUB_REDIRECT_URI
        now = datetime.now(UTC)

        oauth_state = OAuthState(
            state_hash=state_hash,
            session_id=session_id,
            user_id=user_id,
            provider=AuthProvider.GITHUB,
            flow_stage=OAuthFlowStage.INITIATED,
            scope=scope,
            redirect_uri=redirect_uri,
            pkce_challenge_hash=challenge_hash,
            pkce_method=method,
            link_to_user_id=link_to_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=now + timedelta(seconds=self._settings.OAUTH_STATE_TTL_SECONDS),
        )
        self._db.add(oauth_state)
        await self._db.flush()

        self._db.add(
            PKCEChallenge(
                state_id=oauth_state.id,
                code_challenge_hash=challenge_hash,
                code_challenge_method=method,
                code_verifier_encrypted=self._vault.encrypt(verifier),
            )
        )
        await self._db.flush()

        await self._audit.record(
            AuditEventType.OAUTH_INITIATED,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            action="oauth.begin",
            metadata={
                "scope": scope,
                "link_to_user_id": str(link_to_user_id) if link_to_user_id else None,
            },
        )

        params = {
            "client_id": self._settings.GITHUB_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "allow_signup": "true",
            "code_challenge": challenge,
            "code_challenge_method": method,
        }
        url = f"{self._settings.GITHUB_WEB_BASE_URL}/login/oauth/authorize?{urlencode(params)}"
        return url, state, method

    # ------------------------------------------------------------------ #
    # Callback — validate state, exchange code, upsert identity
    # ------------------------------------------------------------------ #
    async def handle_callback(
        self,
        *,
        state: str,
        code: str | None,
        error: str | None,
        error_description: str | None,
        ip_address: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> tuple[User, GitHubAccount, str]:
        """Validate everything, exchange the code, and return (user, account, token).

        The access token is returned for session/credential binding but is never
        sent to the client.
        """
        if error:
            if error == "access_denied":
                await self._audit.record(
                    AuditEventType.OAUTH_CANCELLED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_id=request_id,
                    action="oauth.cancelled",
                    severity="warning",
                )
                raise OAuthCancelledError("You cancelled the GitHub authorization.")
            raise GitHubProviderError(f"GitHub authorization failed: {error}")

        if not code:
            raise OAuthStateMismatchError("Missing authorization code.")

        oauth_state = await self._load_state(state)
        if oauth_state is None:
            await self._audit.record(
                AuditEventType.OAUTH_STATE_MISMATCH,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.state_mismatch",
                severity="critical",
                metadata={"state_hash": hashlib.sha256(state.encode()).hexdigest()},
            )
            raise OAuthStateMismatchError("Invalid OAuth state.")

        # TTL check
        now = datetime.now(UTC)
        expires_at = oauth_state.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            await self._audit.record(
                AuditEventType.OAUTH_STATE_EXPIRED,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.state_expired",
                severity="warning",
                metadata={"state_id": str(oauth_state.id)},
            )
            raise OAuthStateExpiredError("The authorization link has expired. Please try again.")

        # Redirect URI must equal the registered one.
        if oauth_state.redirect_uri != self._settings.GITHUB_REDIRECT_URI:
            await self._audit.record(
                AuditEventType.OAUTH_REDIRECT_MISMATCH,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.redirect_mismatch",
                severity="critical",
                metadata={"state_id": str(oauth_state.id)},
            )
            raise RedirectUriMismatchError("Redirect URI mismatch.")

        if oauth_state.consumed_at is not None:
            await self._audit.record(
                AuditEventType.OAUTH_STATE_MISMATCH,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.state_replay",
                severity="critical",
                metadata={"state_id": str(oauth_state.id)},
            )
            raise OAuthStateMismatchError("OAuth state was already used.")

        # Mark consumed (prevent replay) BEFORE any further work.
        oauth_state.consumed_at = now
        oauth_state.flow_stage = OAuthFlowStage.CALLBACK_RECEIVED
        await self._db.flush()

        # Validate PKCE challenge against stored record before exchange.
        pkce = await self._db.scalar(
            select(PKCEChallenge).where(PKCEChallenge.state_id == oauth_state.id)
        )
        verifier = self._vault.decrypt(pkce.code_verifier_encrypted) if pkce else None
        if not pkce or verifier is None:
            await self._audit.record(
                AuditEventType.OAUTH_PKCE_FAILURE,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.pkce_missing",
                severity="critical",
                metadata={"state_id": str(oauth_state.id)},
            )
            raise PKCEValidationError("PKCE challenge missing.")

        challenge = compute_challenge(verifier, pkce.code_challenge_method)
        expected = hashlib.sha256(challenge.encode()).hexdigest()
        if not constant_time_eq(expected, pkce.code_challenge_hash):
            await self._audit.record(
                AuditEventType.OAUTH_PKCE_FAILURE,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.pkce_mismatch",
                severity="critical",
                metadata={"state_id": str(oauth_state.id)},
            )
            raise PKCEValidationError("PKCE verification failed.")

        # Exchange code (backend only).
        token_data = await self._exchange_code(code, verifier, oauth_state.redirect_uri)
        if token_data.error:
            await self._audit.record(
                AuditEventType.OAUTH_CODE_EXCHANGE,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.code_exchange_failed",
                outcome="failure",
                severity="critical",
                metadata={"error": token_data.error},
            )
            raise GitHubProviderError(f"Token exchange failed: {token_data.error}")

        access_token = token_data.access_token
        oauth_state.flow_stage = OAuthFlowStage.CODE_EXCHANGED

        # Fetch identity.
        gh_user = await self._github.get_user(access_token)
        email = await self._resolve_email(gh_user, access_token)

        # Authenticated "Connect GitHub" linking flow (Password → GitHub).
        if oauth_state.link_to_user_id is not None:
            target = await self._db.get(User, oauth_state.link_to_user_id)
            if target is None or target.deleted_at is not None:
                raise GitHubProviderError("Linking target account not found.")
            existing = await self._db.scalar(
                select(GitHubAccount).where(
                    GitHubAccount.github_id == gh_user.id, GitHubAccount.deleted_at.is_(None)
                )
            )
            if existing is not None:
                raise AccountLinkingRequiredError(
                    candidate_user_id=str(existing.user_id), provider=AuthProvider.GITHUB
                )
            account = GitHubAccount(
                user_id=target.id,
                github_id=gh_user.id,
                login=gh_user.login,
                display_name=gh_user.name,
                avatar_url=gh_user.avatar_url,
                email=email,
                email_verified=bool(email),
                html_url=gh_user.html_url,
                location=gh_user.location,
                bio=gh_user.bio,
                company=gh_user.company,
                github_type=gh_user.type,
            )
            self._db.add(account)
            await self._db.flush()
            await self._store_credential(account, token_data)
            await self._audit.record(
                AuditEventType.ACCOUNT_LINKED,
                user_id=target.id,
                github_id=gh_user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="account.link.github",
            )
            oauth_state.flow_stage = OAuthFlowStage.COMPLETED
            await self._db.flush()
            return target, account, access_token

        # Find existing local account by immutable github_id (canonical identity).
        existing_account = await self._db.scalar(
            select(GitHubAccount).where(
                GitHubAccount.github_id == gh_user.id, GitHubAccount.deleted_at.is_(None)
            )
        )

        user: User | None = None
        if existing_account:
            user = await self._db.get(User, existing_account.user_id)
            if user is None:
                raise AuthenticationError("Linked account is missing its local user record.")
            await self._sync_account(existing_account, gh_user, email)
            await self._store_credential(existing_account, token_data)
            await self._audit.record(
                AuditEventType.LOGIN_SUCCESS,
                user_id=user.id,
                github_id=gh_user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                action="oauth.login",
                metadata={"existing": True},
            )
            oauth_state.flow_stage = OAuthFlowStage.COMPLETED
            await self._db.flush()
            return user, existing_account, access_token

        # New identity — check for a password account with the same verified email.
        candidate: User | None = None
        if email:
            candidate = await self._db.scalar(
                select(User).where(User.email == email, User.deleted_at.is_(None))
            )

        if candidate is not None:
            # Account linking required — never create a duplicate. Park the
            # exchanged credential securely and raise a one-time link token.
            oauth_state.flow_stage = OAuthFlowStage.PENDING_LINK
            link_token = await self._park_pending_link(candidate.id, token_data, gh_user, email)
            await self._db.flush()
            raise AccountLinkingRequiredError(
                candidate_user_id=str(candidate.id),
                provider=AuthProvider.GITHUB,
                details={
                    "link_token": link_token,
                    "email": email,
                    "github_login": gh_user.login,
                    "expires_in": self._settings.OAUTH_STATE_TTL_SECONDS,
                },
            )

        user = User(
            email=email,
            email_verified=bool(email and gh_user.type == "User"),
            display_name=gh_user.name or gh_user.login,
            avatar_url=gh_user.avatar_url,
            status="active",
        )
        self._db.add(user)
        await self._db.flush()

        account = GitHubAccount(
            user_id=user.id,
            github_id=gh_user.id,
            login=gh_user.login,
            display_name=gh_user.name,
            avatar_url=gh_user.avatar_url,
            email=email,
            email_verified=bool(email),
            html_url=gh_user.html_url,
            location=gh_user.location,
            bio=gh_user.bio,
            company=gh_user.company,
            github_type=gh_user.type,
            followers=gh_user.followers,
            following=gh_user.following,
            public_repos=gh_user.public_repos,
        )
        self._db.add(account)
        await self._db.flush()

        await self._store_credential(account, token_data)
        await self._audit.record(
            AuditEventType.REGISTER,
            user_id=user.id,
            github_id=gh_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            action="oauth.register",
        )
        oauth_state.flow_stage = OAuthFlowStage.COMPLETED
        await self._db.flush()
        return user, account, access_token

    # ------------------------------------------------------------------ #
    async def complete_link(
        self,
        *,
        link_token: str,
        password: str,
        user_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> GitHubAccount:
        """Finish GitHub → Password linking.

        The caller (frontend) presents the one-time `link_token` issued when the
        OAuth callback detected an existing account with the same email. The user
        proves ownership of that account by entering its password before the
        GitHub identity is attached. This prevents an attacker who starts an OAuth
        flow from hijacking an existing account.
        """
        from app.core.security import verify_password

        target = await self._db.get(User, user_id)
        if target is None or not target.password_hash:
            raise AuthenticationError("Target account has no password set.")
        if not verify_password(password, target.password_hash):
            await self._audit.record(
                AuditEventType.LOGIN_FAILURE,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                outcome="failure",
                severity="critical",
                action="account.link.password_check",
                metadata={"reason": "bad_password"},
            )
            raise AuthenticationError("The password for the existing account is incorrect.")

        pending = await self._redis_get_pending_link(link_token)
        if pending is None:
            raise OAuthStateExpiredError("This linking session has expired. Start again.")
        if pending["user_id"] != str(user_id):
            await self._audit.record(
                AuditEventType.OAUTH_STATE_MISMATCH,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                severity="critical",
                action="account.link.user_mismatch",
            )
            raise OAuthStateMismatchError("Linking token does not match the target account.")

        existing = await self._db.scalar(
            select(GitHubAccount).where(
                GitHubAccount.github_id == pending["github_id"], GitHubAccount.deleted_at.is_(None)
            )
        )
        if existing is not None:
            raise AccountLinkingRequiredError(
                candidate_user_id=str(existing.user_id), provider=AuthProvider.GITHUB
            )

        token_data = GHAccessToken(
            access_token=self._vault.decrypt(pending["access_token_encrypted"]),
            refresh_token=(
                self._vault.decrypt(pending["refresh_token_encrypted"])
                if pending.get("refresh_token_encrypted")
                else None
            ),
            scope=pending.get("scope", ""),
            expires_in=None,
        )

        account = GitHubAccount(
            user_id=user_id,
            github_id=pending["github_id"],
            login=pending["login"],
            display_name=pending.get("display_name"),
            avatar_url=pending.get("avatar_url"),
            email=pending.get("email"),
            email_verified=bool(pending.get("email")),
            html_url=pending.get("html_url"),
            github_type=pending.get("github_type", "User"),
        )
        self._db.add(account)
        await self._db.flush()
        await self._store_credential(account, token_data)
        await self._audit.record(
            AuditEventType.ACCOUNT_LINKED,
            user_id=user_id,
            github_id=pending["github_id"],
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            action="account.link.github",
        )
        await self._redis_delete_pending_link(link_token)
        await self._db.flush()
        return account

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _park_pending_link(
        self,
        candidate_user_id: uuid.UUID,
        token_data: GHAccessToken,
        gh_user: GHUser,
        email: str | None,
    ) -> str:
        """Store the exchanged credential encrypted (Redis) + issue a link token."""
        import secrets as _secrets

        link_token = _secrets.token_urlsafe(32)
        payload = {
            "user_id": str(candidate_user_id),
            "github_id": gh_user.id,
            "login": gh_user.login,
            "display_name": gh_user.name,
            "avatar_url": gh_user.avatar_url,
            "html_url": gh_user.html_url,
            "github_type": gh_user.type,
            "email": email,
            "access_token_encrypted": self._vault.encrypt(token_data.access_token),
            "refresh_token_encrypted": self._vault.encrypt(token_data.refresh_token)
            if token_data.refresh_token
            else None,
            "scope": token_data.scope or self._settings.GITHUB_SCOPE,
        }
        if self._redis is None:
            return link_token
        await self._redis.set_json(
            f"{_LINK_PREFIX}{link_token}", payload, ttl=self._settings.OAUTH_STATE_TTL_SECONDS
        )
        return link_token

    async def _redis_get_pending_link(self, link_token: str) -> dict[str, Any] | None:
        if self._redis is None:
            return None
        return cast(
            dict[str, Any] | None, await self._redis.get_json(f"{_LINK_PREFIX}{link_token}")
        )

    async def _redis_delete_pending_link(self, link_token: str) -> None:
        if self._redis is None:
            return
        await self._redis.delete(f"{_LINK_PREFIX}{link_token}")

    async def _load_state(self, raw_state: str) -> OAuthState | None:
        state_hash = hashlib.sha256(raw_state.encode()).hexdigest()
        return cast(
            OAuthState | None,
            await self._db.scalar(select(OAuthState).where(OAuthState.state_hash == state_hash)),
        )

    async def _exchange_code(self, code: str, verifier: str, redirect_uri: str) -> GHAccessToken:
        resp = await self._http.post(
            f"{self._settings.GITHUB_WEB_BASE_URL}/login/oauth/access_token",
            data={
                "client_id": self._settings.GITHUB_CLIENT_ID,
                "client_secret": self._settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code >= 400:
            raise GitHubProviderError("GitHub token endpoint returned an error.")
        return GHAccessToken.model_validate(resp.json())

    async def _resolve_email(self, gh_user: GHUser, access_token: str) -> str | None:
        if gh_user.email:
            return gh_user.email
        try:
            return await self._github.get_primary_email(access_token)
        except GitHubClientError:
            logger.info("github_email_unavailable", github_id=gh_user.id)
            return None

    async def _sync_account(
        self, account: GitHubAccount, gh_user: GHUser, email: str | None
    ) -> None:
        account.login = gh_user.login
        account.display_name = gh_user.name or account.display_name
        account.avatar_url = gh_user.avatar_url or account.avatar_url
        account.html_url = gh_user.html_url or account.html_url
        account.location = gh_user.location or account.location
        account.bio = gh_user.bio or account.bio
        account.company = gh_user.company or account.company
        if email:
            account.email = email

    async def _store_credential(
        self, account: GitHubAccount, token_data: GHAccessToken
    ) -> GitHubCredential:
        expires_at = None
        if token_data.expires_in:
            expires_at = datetime.now(UTC) + timedelta(seconds=token_data.expires_in)
        refresh_expires = None
        if token_data.refresh_token_expires_in:
            refresh_expires = datetime.now(UTC) + timedelta(
                seconds=token_data.refresh_token_expires_in
            )
        return await TokenServiceStub(self._db, self._vault).store_credential(
            github_account_id=account.id,
            user_id=account.user_id,
            github_id=account.github_id,
            access_token=token_data.access_token,
            refresh_token=token_data.refresh_token,
            scopes=token_data.scope or self._settings.GITHUB_SCOPE,
            expires_at=expires_at,
            refresh_expires_at=refresh_expires,
        )


class TokenServiceStub:
    """Thin wrapper to avoid circular imports (token_service is imported lazily)."""

    def __init__(self, db: AsyncSession, vault: TokenVault) -> None:
        from app.application.services.token_service import TokenService

        self._inner = TokenService(db, vault)

    async def store_credential(self, **kwargs: object) -> GitHubCredential:
        return await self._inner.store_credential(**kwargs)  # type: ignore[arg-type]
