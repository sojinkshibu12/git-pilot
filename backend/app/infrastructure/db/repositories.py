"""Data-access repositories (infrastructure layer).

Generic CRUD base + domain repositories. These are the only code touching the
ORM directly; application services depend on repository interfaces.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any, Protocol, cast

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.base import Base, SoftDeleteMixin


class _HasID(Protocol):
    id: uuid.UUID


class Repository[ModelT: Base]:
    """Generic async repository over a SQLAlchemy model."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, obj_id: uuid.UUID, *, include_deleted: bool = False) -> ModelT | None:
        model = cast(type[_HasID], self.model)
        stmt = select(self.model).where(cast(ColumnElement[bool], model.id == obj_id))
        if issubclass(self.model, SoftDeleteMixin) and not include_deleted:
            stmt = stmt.where(cast(ColumnElement[bool], self.model.deleted_at.is_(None)))
        return await self.session.scalar(stmt)  # type: ignore[no-any-return]

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def soft_delete(self, instance: ModelT) -> None:
        if isinstance(instance, SoftDeleteMixin):
            from datetime import datetime

            instance.deleted_at = datetime.now(UTC)
            await self.session.flush()


class UsersRepository(Repository[Any]):
    pass
