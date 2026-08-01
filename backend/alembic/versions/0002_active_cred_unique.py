"""fix active-credential uniqueness to partial index

The original UNIQUE(github_account_id, is_active) constraint capped history at
two rows per account (one active, one inactive), breaking token rotation on the
second rotation. Replace with a partial unique index over active rows only.

Revision ID: 0002_fix_active_credential_unique
Revises: 0001_initial
Create Date: 2026-08-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_active_cred_unique"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_active_credential_per_account",
        "github_credentials",
        type_="unique",
    )
    op.create_index(
        "uq_active_credential_per_account",
        "github_credentials",
        ["github_account_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_active_credential_per_account",
        table_name="github_credentials",
        postgresql_where=sa.text("is_active IS TRUE"),
    )
    op.create_unique_constraint(
        "uq_active_credential_per_account",
        "github_credentials",
        ["github_account_id", "is_active"],
    )
