"""Typed exceptions shared across application + infrastructure layers.

Each carries an HTTP status and a stable machine-readable error code so the API
layer can map them to responses without leaking internals.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str = "Request could not be processed", **details: Any) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_failed"


class SessionExpiredError(AuthenticationError):
    code = "session_expired"


class InvalidSessionError(AuthenticationError):
    code = "invalid_session"


class AuthorizationError(DomainError):
    status_code = 403
    code = "permission_denied"


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class ValidationFailure(DomainError):
    status_code = 422
    code = "validation_failed"


class RateLimitExceeded(DomainError):
    status_code = 429
    code = "rate_limit_exceeded"


class OAuthStateMismatchError(AuthenticationError):
    status_code = 403
    code = "oauth_state_mismatch"


class OAuthStateExpiredError(AuthenticationError):
    status_code = 403
    code = "oauth_state_expired"


class PKCEValidationError(AuthenticationError):
    status_code = 403
    code = "pkce_validation_failed"


class RedirectUriMismatchError(AuthenticationError):
    status_code = 403
    code = "redirect_uri_mismatch"


class OAuthCancelledError(AuthenticationError):
    status_code = 400
    code = "oauth_cancelled"


class GitHubProviderError(DomainError):
    status_code = 502
    code = "github_upstream_error"

    def __init__(self, message: str = "GitHub is unavailable", **details: Any) -> None:
        super().__init__(message, **details)


class GitHubRateLimitedError(GitHubProviderError):
    status_code = 503
    code = "github_rate_limited"


class TokenInvalidError(AuthenticationError):
    code = "token_invalid"


class MissingEmailError(ValidationFailure):
    code = "email_required"


class PendingVerificationError(ConflictError):
    code = "verification_pending"


class AccountLinkingRequiredError(DomainError):
    status_code = 409
    code = "account_linking_required"

    def __init__(
        self,
        *,
        candidate_user_id: str,
        provider: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            "An account with this email already exists. Link it to continue.",
            candidate_user_id=candidate_user_id,
            provider=provider,
            **({"details": details} if details else {}),
        )
