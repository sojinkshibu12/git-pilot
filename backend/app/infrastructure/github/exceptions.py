"""Normalized GitHub upstream errors.

Every upstream failure is wrapped in a typed exception so the API layer can map
it to a stable error code + status without leaking GitHub internals.
"""
from __future__ import annotations

from app.core.exceptions import (
    AuthorizationError,
    GitHubProviderError,
    GitHubRateLimitedError,
    NotFoundError,
    RateLimitExceeded,
    ValidationFailure,
)


class GitHubClientError(Exception):
    """Base class for errors raised by the GitHub client."""

    def __init__(self, message: str, *, status_code: int | None = None, body: dict | None = None) -> None:
        self.status_code = status_code
        self.body = body or {}
        super().__init__(message)


class GitHubAuthError(GitHubClientError):
    """401 — token missing/invalid/revoked."""


class GitHubForbiddenError(GitHubClientError):
    """403 — permission denied or scope insufficient."""


class GitHubNotFoundError(GitHubClientError):
    """404 — resource missing."""


class GitHubRateLimitError(GitHubClientError):
    """429 or 403 with rate-limit headers — quota exhausted."""

    def __init__(self, message: str, *, reset_at: int | None = None, **kw: object) -> None:
        self.reset_at = reset_at
        super().__init__(message, **kw)


class GitHubConflictError(GitHubClientError):
    """409 — state conflict (e.g. repo already exists)."""


class GitHubValidationError(GitHubClientError):
    """422 — validation failed upstream."""


class GitHubServerError(GitHubClientError):
    """5xx — transient upstream failures (retried)."""


class GitHubUnavailableError(GitHubClientError):
    """Transport-level failures (DNS, connection reset, timeout)."""


_STATUS_TO_EXC: dict[int, type[GitHubClientError]] = {
    401: GitHubAuthError,
    403: GitHubForbiddenError,
    404: GitHubNotFoundError,
    409: GitHubConflictError,
    422: GitHubValidationError,
}


def normalize_github_error(status_code: int, body: dict | None) -> GitHubClientError:
    body = body or {}
    message = body.get("message") or f"GitHub API error ({status_code})"
    exc_cls = _STATUS_TO_EXC.get(status_code)
    if exc_cls is not None:
        return exc_cls(message, status_code=status_code, body=body)
    if 500 <= status_code <= 599:
        return GitHubServerError(message, status_code=status_code, body=body)
    return GitHubClientError(message, status_code=status_code, body=body)


def to_domain_exception(exc: GitHubClientError) -> GitHubProviderError:
    """Map a client error to a domain exception understood by the API layer."""
    if isinstance(exc, GitHubRateLimitError):
        return GitHubRateLimitedError(
            "GitHub rate limit reached. Try again shortly.",
            reset_at=exc.reset_at,
        )
    if isinstance(exc, GitHubAuthError):
        return AuthorizationError("GitHub credentials are invalid or expired.")
    if isinstance(exc, GitHubForbiddenError):
        return AuthorizationError("You do not have permission for this GitHub resource.")
    if isinstance(exc, GitHubNotFoundError):
        return NotFoundError("Resource not found on GitHub.")
    if isinstance(exc, GitHubValidationError):
        return ValidationFailure("GitHub rejected the request.", upstream=exc.body)
    if isinstance(exc, GitHubConflictError):
        from app.core.exceptions import ConflictError

        return ConflictError(str(exc))
    return GitHubProviderError("GitHub is unavailable or returned an unexpected error.")
