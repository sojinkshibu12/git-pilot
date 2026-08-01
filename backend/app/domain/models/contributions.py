"""Contribution heatmap entity: per-day contribution counts for a user.

One row per (user, day), mirroring GitHub's contribution calendar. `count` is the
authoritative calendar total for that day (matches the GitHub profile exactly);
the type columns are best-effort breakdowns (commits, PRs, issues, reviews,
repository creations, actions) used to filter the heatmap client-side.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import GUID, Base, _uuid_pk


class Contribution(Base):
    __tablename__ = "contributions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pull_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repository_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_contributions_user_date"),
    )
