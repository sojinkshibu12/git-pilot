"""Domain enums — shared vocabulary for the GitPilot domain.

These are framework-free values consumed by both the ORM and the API schemas.
"""
from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    """str-enum that serializes to its value in JSON by default."""

    def __str__(self) -> str:
        return self.value


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING_EMAIL = "pending_email"
    LOCKED = "locked"
    DELETED = "deleted"


class AuthProvider(StrEnum):
    GITHUB = "github"
    EMAIL = "email"
    GOOGLE = "google"  # future
    MICROSOFT = "microsoft"  # future
    GITLAB = "gitlab"  # future


class SessionStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class OAuthFlowStage(StrEnum):
    INITIATED = "initiated"
    CALLBACK_RECEIVED = "callback_received"
    CODE_EXCHANGED = "code_exchanged"
    PENDING_LINK = "pending_link"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditEventType(StrEnum):
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILURE = "login.failure"
    REGISTER = "register"
    LOGOUT = "logout"
    SESSION_CREATED = "session.created"
    SESSION_REVOKED = "session.revoked"
    SESSION_EXPIRED = "session.expired"
    SESSION_ROTATED = "session.rotated"
    TOKEN_REFRESH = "token.refresh"
    TOKEN_REVOKED = "token.revoked"
    OAUTH_INITIATED = "oauth.initiated"
    OAUTH_STATE_MISMATCH = "oauth.state_mismatch"
    OAUTH_STATE_EXPIRED = "oauth.state_expired"
    OAUTH_PKCE_FAILURE = "oauth.pkce_failure"
    OAUTH_REDIRECT_MISMATCH = "oauth.redirect_mismatch"
    OAUTH_CODE_EXCHANGE = "oauth.code_exchange"
    OAUTH_CANCELLED = "oauth.cancelled"
    ACCOUNT_LINKED = "account.linked"
    ACCOUNT_UNLINKED = "account.unlinked"
    PASSWORD_CHANGED = "password.changed"
    EMAIL_CHANGED = "email.changed"
    EMAIL_VERIFIED = "email.verified"
    MFA_ENABLED = "mfa.enabled"
    MFA_DISABLED = "mfa.disabled"
    REPOSITORY_ACCESS = "repository.access"
    REPOSITORY_MODIFICATION = "repository.modification"
    PERMISSION_CHANGE = "permission.change"
    SCOPE_CHANGE = "scope.change"
    WEBHOOK_EVENT = "webhook.event"
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"
    RATE_LIMIT_HIT = "rate_limit.hit"
    SECURITY_EVENT = "security.event"


class RepoPermission(StrEnum):
    NONE = "none"
    READ = "read"
    TRIAGE = "triage"
    WRITE = "write"
    MAINTAIN = "maintain"
    ADMIN = "admin"


class OrganizationRole(StrEnum):
    MEMBER = "member"
    ADMIN = "admin"
    BILLING_MANAGER = "billing_manager"


class RepositoryVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"


class WebhookEventStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


class GitHubEntityType(StrEnum):
    USER = "user"
    ORGANIZATION = "organization"


class PlanName(StrEnum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"
