"""Abstract repository interfaces for ImpactOS persistence layer.

Repositories call add()/flush()/refresh() only — never commit().
The session dependency handles commit/rollback (Unit-of-Work).
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class AbstractRepository(ABC, Generic[T]):
    """Base repository interface."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @abstractmethod
    async def get(self, entity_id: UUID) -> T | None:
        ...

    @abstractmethod
    async def create(self, entity: T) -> T:
        ...

    @abstractmethod
    async def list_all(self) -> list[T]:
        ...
