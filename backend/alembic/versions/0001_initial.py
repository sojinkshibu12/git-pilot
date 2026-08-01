"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # users
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("last_login_at", _TS, nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    # ------------------------------------------------------------------ #
    # github_accounts
    # ------------------------------------------------------------------ #
    op.create_table(
        "github_accounts",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("github_id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("html_url", sa.String(length=1024), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("github_type", sa.String(length=32), nullable=False, server_default="User"),
        sa.Column("plan", sa.String(length=64), nullable=True),
        sa.Column("organizations_json", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("followers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("following", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("public_repos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_github_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_github_accounts_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_github_accounts"),
        sa.UniqueConstraint("user_id", "github_id", name="uq_github_accounts_user_github"),
    )
    op.create_index("ix_github_accounts_github_id", "github_accounts", ["github_id"], unique=True)
    op.create_index("ix_github_accounts_login", "github_accounts", ["login"])
    op.create_index("ix_github_accounts_user_id", "github_accounts", ["user_id"])

    # ------------------------------------------------------------------ #
    # sessions
    # ------------------------------------------------------------------ #
    op.create_table(
        "sessions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", _TS, nullable=True),
        sa.Column("last_used_at", _TS, nullable=True),
        sa.Column("rotated_at", _TS, nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("device_label", sa.String(length=255), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )
    op.create_index("ix_sessions_session_token_hash", "sessions", ["session_token_hash"], unique=True)
    op.create_index("ix_sessions_status", "sessions", ["status"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_user_status", "sessions", ["user_id", "status"])

    # ------------------------------------------------------------------ #
    # oauth_states
    # ------------------------------------------------------------------ #
    op.create_table(
        "oauth_states",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("state_hash", sa.Text(), nullable=False),
        sa.Column("session_id", _UUID, nullable=True),
        sa.Column("user_id", _UUID, nullable=True),
        sa.Column("provider", sa.String(length=24), nullable=False, server_default="github"),
        sa.Column("flow_stage", sa.String(length=24), nullable=False, server_default="initiated"),
        sa.Column("scope", sa.String(length=512), nullable=False),
        sa.Column("redirect_uri", sa.String(length=1024), nullable=False),
        sa.Column("pkce_challenge_hash", sa.Text(), nullable=False),
        sa.Column("pkce_method", sa.String(length=8), nullable=False, server_default="S256"),
        sa.Column("link_to_user_id", _UUID, nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("consumed_at", _TS, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_states"),
    )
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])
    op.create_index("ix_oauth_states_session_id", "oauth_states", ["session_id"])
    op.create_index("ix_oauth_states_session_created", "oauth_states", ["session_id", "created_at"])
    op.create_index("ix_oauth_states_state_hash", "oauth_states", ["state_hash"], unique=True)
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])

    # ------------------------------------------------------------------ #
    # pkce_challenges
    # ------------------------------------------------------------------ #
    op.create_table(
        "pkce_challenges",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("state_id", _UUID, nullable=False),
        sa.Column("code_challenge_hash", sa.Text(), nullable=False),
        sa.Column("code_challenge_method", sa.String(length=8), nullable=False, server_default="S256"),
        sa.Column("code_verifier_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("consumed_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["state_id"], ["oauth_states.id"], name="fk_pkce_challenges_state_id_oauth_states", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_pkce_challenges"),
    )
    op.create_index("ix_pkce_challenges_state_id", "pkce_challenges", ["state_id"], unique=True)

    # ------------------------------------------------------------------ #
    # refresh_tokens
    # ------------------------------------------------------------------ #
    op.create_table(
        "refresh_tokens",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("github_account_id", _UUID, nullable=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=16), nullable=False, server_default="refresh"),
        sa.Column("scopes", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("expires_at", _TS, nullable=True),
        sa.Column("replaced_by", _UUID, nullable=True),
        sa.Column("revoked_at", _TS, nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["github_account_id"], ["github_accounts.id"], name="fk_refresh_tokens_github_account_id_github_accounts", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
    )
    op.create_index("ix_refresh_tokens_github_account_id", "refresh_tokens", ["github_account_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_user_created", "refresh_tokens", ["user_id", "created_at"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # ------------------------------------------------------------------ #
    # api_keys
    # ------------------------------------------------------------------ #
    op.create_table(
        "api_keys",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("scopes", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("last_used_at", _TS, nullable=True),
        sa.Column("expires_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_api_keys_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    # ------------------------------------------------------------------ #
    # user_preferences
    # ------------------------------------------------------------------ #
    op.create_table(
        "user_preferences",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("theme", sa.String(length=16), nullable=False, server_default="system"),
        sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_repo_visibility", sa.String(length=16), nullable=False, server_default="private"),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_preferences_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_user_preferences"),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True)

    # ------------------------------------------------------------------ #
    # audit_logs
    # ------------------------------------------------------------------ #
    op.create_table(
        "audit_logs",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", _UUID, nullable=True),
        sa.Column("github_id", sa.Integer(), nullable=True),
        sa.Column("session_id", _UUID, nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="success"),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_correlation", "audit_logs", ["correlation_id", "created_at"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"])
    op.create_index("ix_audit_logs_user_event", "audit_logs", ["user_id", "event_type", "created_at"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    # ------------------------------------------------------------------ #
    # organizations / membership
    # ------------------------------------------------------------------ #
    op.create_table(
        "organizations",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("html_url", sa.String(length=1024), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=False, server_default="member"),
        sa.Column("members_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repos_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
    )
    op.create_index("ix_organizations_github_id", "organizations", ["github_id"], unique=True)
    op.create_index("ix_organizations_login", "organizations", ["login"])

    op.create_table(
        "organization_members",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False, server_default="member"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_organization_members_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_organization_members_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_organization_members"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_members_org_user"),
    )
    op.create_index("ix_organization_members_organization_id", "organization_members", ["organization_id"])
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])

    # ------------------------------------------------------------------ #
    # repositories
    # ------------------------------------------------------------------ #
    op.create_table(
        "repositories",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", _UUID, nullable=True),
        sa.Column("github_account_id", _UUID, nullable=True),
        sa.Column("full_name", sa.String(length=300), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("owner_login", sa.String(length=255), nullable=False),
        sa.Column("owner_type", sa.String(length=24), nullable=False, server_default="User"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="private"),
        sa.Column("private", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("html_url", sa.String(length=1024), nullable=False),
        sa.Column("ssh_url", sa.String(length=1024), nullable=True),
        sa.Column("clone_url", sa.String(length=1024), nullable=True),
        sa.Column("default_branch", sa.String(length=255), nullable=False, server_default="main"),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("fork", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stars_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topics", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("last_synced_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["github_account_id"], ["github_accounts.id"], name="fk_repositories_github_account_id_github_accounts", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_repositories_owner_user_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_repositories"),
        sa.UniqueConstraint("github_id", "full_name", name="uq_repositories_github_full"),
    )
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"])
    op.create_index("ix_repositories_github_account_id", "repositories", ["github_account_id"])
    op.create_index("ix_repositories_github_id", "repositories", ["github_id"], unique=True)
    op.create_index("ix_repositories_owner_login", "repositories", ["owner_login"])
    op.create_index("ix_repositories_owner_login_name", "repositories", ["owner_login", "name"])
    op.create_index("ix_repositories_owner_user_id", "repositories", ["owner_user_id"])

    # ------------------------------------------------------------------ #
    # repository_permissions
    # ------------------------------------------------------------------ #
    op.create_table(
        "repository_permissions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("repository_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("permission", sa.String(length=16), nullable=False, server_default="read"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("granted_by", sa.String(length=24), nullable=False, server_default="github"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="api"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], name="fk_repository_permissions_repository_id_repositories", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_repository_permissions_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_repository_permissions"),
        sa.UniqueConstraint("repository_id", "user_id", name="uq_repo_permissions_repo_user"),
    )
    op.create_index("ix_repository_permissions_repository_id", "repository_permissions", ["repository_id"])
    op.create_index("ix_repository_permissions_user_id", "repository_permissions", ["user_id"])

    # ------------------------------------------------------------------ #
    # webhook_installations
    # ------------------------------------------------------------------ #
    op.create_table(
        "webhook_installations",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=True),
        sa.Column("repository_id", _UUID, nullable=True),
        sa.Column("organization_id", _UUID, nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("events", postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_delivery_at", _TS, nullable=True),
        sa.Column("last_delivery_status", sa.String(length=32), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_webhook_installations_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], name="fk_webhook_installations_repository_id_repositories", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_installations"),
    )
    op.create_index("ix_webhook_installations_github_id", "webhook_installations", ["github_id"], unique=True)
    op.create_index("ix_webhook_installations_organization_id", "webhook_installations", ["organization_id"])
    op.create_index("ix_webhook_installations_repository_id", "webhook_installations", ["repository_id"])

    # ------------------------------------------------------------------ #
    # github_credentials (encrypted token vault)
    # ------------------------------------------------------------------ #
    op.create_table(
        "github_credentials",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("github_account_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("scopes", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("expires_at", _TS, nullable=True),
        sa.Column("refresh_expires_at", _TS, nullable=True),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("encryption_metadata", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", _TS, nullable=True),
        sa.ForeignKeyConstraint(["github_account_id"], ["github_accounts.id"], name="fk_github_credentials_github_account_id_github_accounts", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_github_credentials_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_github_credentials"),
    )
    op.create_index("ix_github_credentials_github_account_id", "github_credentials", ["github_account_id"])
    op.create_index("ix_github_credentials_github_id", "github_credentials", ["github_id"])
    op.create_index("ix_github_credentials_user_id", "github_credentials", ["user_id"])
    op.create_index(
        "uq_active_credential_per_account",
        "github_credentials",
        ["github_account_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_table("github_credentials")
    op.drop_table("webhook_installations")
    op.drop_table("repository_permissions")
    op.drop_table("repositories")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("audit_logs")
    op.drop_table("user_preferences")
    op.drop_table("api_keys")
    op.drop_table("refresh_tokens")
    op.drop_table("pkce_challenges")
    op.drop_table("oauth_states")
    op.drop_table("sessions")
    op.drop_table("github_accounts")
    op.drop_table("users")
