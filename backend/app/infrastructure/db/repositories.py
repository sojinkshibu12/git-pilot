"""Data-access repositories (infrastructure layer).

Generic CRUD base + domain repositories. These are the only code touching the
ORM directly; application services depend on repository interfaces.
"""
from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.base import Base, SoftDeleteMixin

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    """Generic async repository over a SQLAlchemy model."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, obj_id: uuid.UUID, *, include_deleted: bool = False) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == obj_id)
        if issubclass(self.model, SoftDeleteMixin) and not include_deleted:
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return await self.session.scalar(stmt)

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def soft_delete(self, instance: ModelT) -> None:
        if isinstance(instance, SoftDeleteMixin):
            from datetime import datetime, timezone

            instance.deleted_at = datetime.now(timezone.utc)
            await self.session.flush()


class UsersRepository(Repository[Any]):
    pass
