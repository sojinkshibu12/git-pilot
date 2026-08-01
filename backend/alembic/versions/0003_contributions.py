"""add contributions heatmap table

Stores per-day contribution counts (calendar total + per-type breakdown) so the
dashboard heatmap and its statistics can be served from the database without
hitting the GitHub API on every page load.

Revision ID: 0003_contributions
Revises: 0002_active_cred_unique
Create Date: 2026-08-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_contributions"
down_revision = "0002_active_cred_unique"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "contributions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pull_request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repository_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_contributions_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_contributions"),
        sa.UniqueConstraint("user_id", "date", name="uq_contributions_user_date"),
    )
    op.create_index("ix_contributions_user_id", "contributions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_contributions_user_id", table_name="contributions")
    op.drop_table("contributions")
