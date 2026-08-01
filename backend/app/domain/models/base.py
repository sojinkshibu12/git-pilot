"""SQLAlchemy 2 declarative base with shared column conventions.

- UUID primary keys (server-generated `gen_random_uuid()` on Postgres)
- CreatedAt / UpdatedAt / DeletedAt on every table (soft deletes)
- Named constraint conventions so Alembic renders deterministic migrations
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent GUID that uses native UUID on Postgres."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PgUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: uuid.UUID | None, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = uuid.UUID(value)
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)

    def dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SoftDeleteMixin(TimestampMixin):
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
