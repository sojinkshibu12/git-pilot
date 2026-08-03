"""GitHub App authentication service (server-to-server).

Resolves a GitHub App installation for a given owner/repo and issues short-lived
*installation access tokens* that carry the app's permissions (issues, PRs,
contents, ...). Tokens are cached in Redis near their expiry to avoid hammering
the GitHub API.

Authentication flow (all API calls below authenticate with the app JWT):
1. Sign a JWT with the app's private key (RS256) — see `core.github_app_jwt`.
2. Resolve the installation id for an owner/repo:
   `GET /repos/{owner}/{repo}/installation` (or `GET /users/{o}/installation`,
   `GET /orgs/{o}/installation`), falling back to listing `/app/installations`.
3. Issue an access token: `POST /app/installations/{id}/access_tokens`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings
from app.core.github_app_jwt import sign_app_jwt
from app.core.logging import get_logger
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.github.exceptions import GitHubClientError, GitHubNotFoundError
from app.infrastructure.github.models import GHInstallation, GHInstallationToken, GHRepository
from app.infrastructure.redis.client import RedisClient

logger = get_logger("github-app")

_INSTALL_ID_CACHE_PREFIX = "gp:install:"
_TOKEN_CACHE_PREFIX = "gp:install-token:"  # noqa: S105 - redis key, not a password
# Re-issue the token when less than this many seconds remain (GitHub tokens live 1h).
_TOKEN_REISSUE_LEEWAY = 300


class GitHubAppAuthError(GitHubClientError):
    """Raised when GitHub App auth cannot be established."""


class GitHubAppAuthService:
    def __init__(
        self,
        *,
        settings: Settings,
        github: GitHubAPIClient,
        redis: RedisClient,
    ) -> None:
        self._settings = settings
        self._github = github
        self._redis = redis

    # ------------------------------------------------------------------ #
    # App JWT
    # ------------------------------------------------------------------ #
    def create_app_jwt(self, *, now: datetime | None = None) -> str:
        """Sign a fresh app JWT with the configured private key."""
        key = self._settings.github_private_key()
        if not key:
            raise GitHubAppAuthError("GitHub App private key is not configured")
        app_id = self._settings.GITHUB_APP_ID
        if not app_id:
            raise GitHubAppAuthError("GITHUB_APP_ID is not configured")
        return sign_app_jwt(app_id, key, now=now)

    # ------------------------------------------------------------------ #
    # Installation resolution
    # ------------------------------------------------------------------ #
    async def installation_id_for(self, owner: str, repo: str | None = None) -> int:
        """Return the installation id covering the given owner/repo.

        Uses `GITHUB_APP_INSTALLATION_ID` when set, otherwise resolves it via the
        GitHub API and caches the mapping per owner.
        """
        fixed = self._settings.GITHUB_APP_INSTALLATION_ID
        if fixed:
            return fixed

        cache_key = f"{_INSTALL_ID_CACHE_PREFIX}{owner.lower()}"
        cached = await self._redis.get_json(cache_key)
        if isinstance(cached, int):
            return cached

        installation = await self._resolve_installation(owner, repo)
        await self._redis.set_json(
            cache_key, installation.id, ttl=self._settings.GH_CACHE_TTL_SECONDS
        )
        return installation.id

    async def _resolve_installation(self, owner: str, repo: str | None) -> GHInstallation:
        app_jwt = self.create_app_jwt()
        candidates = [
            f"/repos/{owner}/{repo}/installation" if repo else None,
            f"/orgs/{owner}/installation",
            f"/users/{owner}/installation",
        ]
        for path in candidates:
            if not path:
                continue
            try:
                resp = await self._github.request("GET", path, app_jwt)
                return GHInstallation.model_validate(resp.json())
            except GitHubNotFoundError:
                continue

        # Fall back to a full listing (handles installations on any owner type).
        return await self._find_installation_in_list(app_jwt, owner)

    async def _find_installation_in_list(self, app_jwt: str, owner: str) -> GHInstallation:
        try:
            resp = await self._github.request(
                "GET", "/app/installations", app_jwt, params={"per_page": 100}
            )
        except GitHubNotFoundError as exc:
            raise GitHubAppAuthError(f"GitHub App is not installed for '{owner}'") from exc
        data = resp.json()
        records = data if isinstance(data, list) else data.get("installations", [])
        for record in records:
            account = record.get("account") or {}
            if str(account.get("login", "")).lower() == owner.lower():
                return GHInstallation.model_validate(record)
        raise GitHubAppAuthError(f"GitHub App is not installed for '{owner}'")

    # ------------------------------------------------------------------ #
    # Installation access tokens
    # ------------------------------------------------------------------ #
    async def installation_token_for(self, owner: str, repo: str | None = None) -> str:
        """Return a cached (or freshly issued) installation access token."""
        installation_id = await self.installation_id_for(owner, repo)
        cache_key = f"{_TOKEN_CACHE_PREFIX}{installation_id}"

        cached = await self._redis.get_json(cache_key)
        if isinstance(cached, dict):
            token = cached.get("token")
            expires_at = cached.get("expires_at")
            if (
                isinstance(token, str)
                and isinstance(expires_at, str)
                and self._token_still_valid(expires_at)
            ):
                return token

        token_data = await self._issue_token(installation_id)
        ttl = self._token_ttl_seconds(token_data.expires_at)
        if ttl > 0:
            await self._redis.set_json(
                cache_key,
                {
                    "token": token_data.token,
                    "expires_at": token_data.expires_at.isoformat()
                    if token_data.expires_at
                    else None,
                },
                ttl=ttl,
            )
        return token_data.token

    async def _issue_token(self, installation_id: int) -> GHInstallationToken:
        app_jwt = self.create_app_jwt()
        try:
            resp = await self._github.request(
                "POST", f"/app/installations/{installation_id}/access_tokens", app_jwt
            )
        except GitHubClientError as exc:
            logger.warning(
                "github_app_token_issue_failed",
                installation_id=installation_id,
                error=exc.__class__.__name__,
            )
            raise GitHubAppAuthError(
                f"Failed to issue installation access token for installation {installation_id}"
            ) from exc
        return GHInstallationToken.model_validate(resp.json())

    # ------------------------------------------------------------------ #
    # Installed repositories
    # ------------------------------------------------------------------ #
    async def list_installation_repositories(
        self, owner: str | None = None, repo: str | None = None
    ) -> list[GHRepository]:
        """List repositories the installation can access (needs a token first)."""
        target = owner or self._default_owner()
        token = await self.installation_token_for(target, repo)
        resp = await self._github.request(
            "GET", "/installation/repositories", token, params={"per_page": 100}
        )
        data = resp.json()
        records = data.get("repositories", []) if isinstance(data, dict) else []
        return [GHRepository.model_validate(r) for r in records]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _default_owner(self) -> str:
        raise GitHubAppAuthError("An owner is required to resolve the GitHub App installation")

    @staticmethod
    def _token_still_valid(expires_at: str | None) -> bool:
        if not expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
        except ValueError:
            return False
        return (expiry - datetime.now(UTC)).total_seconds() > _TOKEN_REISSUE_LEEWAY

    @staticmethod
    def _token_ttl_seconds(expires_at: datetime | None) -> int:
        if not expires_at:
            return 0
        expiry = expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        remaining = int((expiry - datetime.now(UTC)).total_seconds()) - _TOKEN_REISSUE_LEEWAY
        return max(0, remaining)
