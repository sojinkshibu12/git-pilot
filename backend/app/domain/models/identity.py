"""Core identity + OAuth + session entities.

All tables use UUID primary keys, FK + unique constraints, indexes, and soft
deletes via `deleted_at`. Never identify a user by email or username — the
immutable GitHub numeric ID is the canonical external identity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.models.base import GUID, Base, SoftDeleteMixin, _uuid_pk
from app.domain.models.enums import (
    AuthProvider,
    OAuthFlowStage,
    SessionStatus,
    TokenType,
    UserStatus,
)

if TYPE_CHECKING:
    from app.domain.models.github import Repository


class User(Base, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=UserStatus.ACTIVE)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")

    github_accounts: Mapped[list[GitHubAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    repositories: Mapped[list[Repository]] = relationship(back_populates="owner")

    __table_args__ = (Index("ix_users_email_lower", text("lower(email)"), unique=True),)


class GitHubAccount(Base, SoftDeleteMixin):
    """An immutable GitHub identity bound to a User.

    The `github_id` is the numeric GitHub user id — the canonical identifier.
    """

    __tablename__ = "github_accounts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    login: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    html_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_type: Mapped[str] = mapped_column(String(32), nullable=False, default="User")
    plan: Mapped[str | None] = mapped_column(String(64), nullable=True)
    organizations_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    followers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    following: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    public_repos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_github_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="github_accounts")
    repositories: Mapped[list[Repository]] = relationship(back_populates="github_account")

    __table_args__ = (
        UniqueConstraint("user_id", "github_id", name="uq_github_accounts_user_github"),
    )


class Session(Base, SoftDeleteMixin):
    """Server-side session. The cookie only stores the session id (opaque)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        String(16), nullable=False, default=SessionStatus.ACTIVE, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    device_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (Index("ix_sessions_user_status", "user_id", "status"),)


class OAuthState(Base):
    """Server-side record of an initiated OAuth authorization request.

    Binds the `state` nonce to a session, records the PKCE challenge and the
    exact (registered) redirect URI, and enforces a 10-minute TTL.
    """

    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = _uuid_pk()
    state_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    provider: Mapped[AuthProvider] = mapped_column(
        String(24), nullable=False, default=AuthProvider.GITHUB
    )
    flow_stage: Mapped[OAuthFlowStage] = mapped_column(
        String(24), nullable=False, default=OAuthFlowStage.INITIATED
    )
    scope: Mapped[str] = mapped_column(String(512), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    pkce_challenge_hash: Mapped[str] = mapped_column(Text, nullable=False)
    pkce_method: Mapped[str] = mapped_column(String(8), nullable=False, default="S256")
    link_to_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_oauth_states_session_created", "session_id", "created_at"),)


class PKCEChallenge(Base):
    """Server-side PKCE challenge storage (RFC 7636).

    The verifier itself is stored encrypted; it is only used at the moment of
    token exchange and deleted immediately afterwards.
    """

    __tablename__ = "pkce_challenges"

    id: Mapped[uuid.UUID] = _uuid_pk()
    state_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("oauth_states.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    code_challenge_hash: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(8), nullable=False, default="S256")
    code_verifier_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base, SoftDeleteMixin):
    """Server-side refresh-token records (used for GitHub App tokens)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("github_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_type: Mapped[TokenType] = mapped_column(
        String(16), nullable=False, default=TokenType.REFRESH
    )
    scopes: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_refresh_tokens_user_created", "user_id", "created_at"),)


class APIKey(Base, SoftDeleteMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    email_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_repo_visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private"
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    github_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )

    __table_args__ = (
        Index("ix_audit_logs_user_event", "user_id", "event_type", "created_at"),
        Index("ix_audit_logs_correlation", "correlation_id", "created_at"),
    )
