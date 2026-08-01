"""GitHub domain entities: organizations, repositories, permissions, webhooks.

These mirror GitHub's upstream models so the platform can migrate between OAuth
Apps and GitHub Apps without schema churn.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
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
    OrganizationRole,
    RepoPermission,
    RepositoryVisibility,
)

if TYPE_CHECKING:
    from app.domain.models.identity import GitHubAccount, User


class Organization(Base, SoftDeleteMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    login: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    role: Mapped[OrganizationRole] = mapped_column(
        String(24), nullable=False, default=OrganizationRole.MEMBER
    )
    members_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repos_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", passive_deletes=True
    )


class OrganizationMember(Base):
    """Membership of a local user in a synced GitHub organization."""

    __tablename__ = "organization_members"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[OrganizationRole] = mapped_column(
        String(24), nullable=False, default=OrganizationRole.MEMBER
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    organization: Mapped[Organization] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_members_org_user"),
    )


class Repository(Base, SoftDeleteMixin):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    github_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("github_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_login: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_type: Mapped[str] = mapped_column(String(24), nullable=False, default="User")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[RepositoryVisibility] = mapped_column(
        String(16), nullable=False, default=RepositoryVisibility.PRIVATE
    )
    private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    html_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    ssh_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    clone_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fork: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stars_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    forks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User | None] = relationship(back_populates="repositories")
    github_account: Mapped[GitHubAccount | None] = relationship(back_populates="repositories")
    permissions: Mapped[list["RepositoryPermission"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("github_id", "full_name", name="uq_repositories_github_full"),
        Index("ix_repositories_owner_login_name", "owner_login", "name"),
    )


class RepositoryPermission(Base, SoftDeleteMixin):
    """Effective permission of a local user on a synced repository.

    `permission` reflects GitHub's mapping (read/triage/write/maintain/admin).
    """

    __tablename__ = "repository_permissions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission: Mapped[RepoPermission] = mapped_column(
        String(16), nullable=False, default=RepoPermission.READ
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    granted_by: Mapped[str] = mapped_column(String(24), nullable=False, default="github")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="api")

    repository: Mapped[Repository] = relationship(back_populates="permissions")

    __table_args__ = (
        UniqueConstraint("repository_id", "user_id", name="uq_repo_permissions_repo_user"),
    )


class WebhookInstallation(Base, SoftDeleteMixin):
    """Webhook deliveries for repositories / orgs (OAuth App or GitHub App)."""

    __tablename__ = "webhook_installations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    github_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True, index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class GitHubCredential(Base, SoftDeleteMixin):
    """Encrypted GitHub credential material for an account.

    Never stores plaintext tokens. Access tokens are AES-256-GCM encrypted via
    the TokenVault; the record carries encryption metadata + token version for
    rotation and migration.
    """

    __tablename__ = "github_credentials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    github_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("github_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One active credential row per account.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    encryption_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        # Partial unique index: at most one ACTIVE credential per account.
        # Inactive (rotated/revoked) rows may accumulate without conflict.
        Index(
            "uq_active_credential_per_account",
            "github_account_id",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
        ),
    )
