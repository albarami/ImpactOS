"""Store ABCs and in-memory implementations for the Knowledge Flywheel.

Provides two abstract store contracts:
- ``VersionedLibraryStore`` for storing versioned library snapshots
  (mapping libraries, assumption libraries, workforce libraries).
- ``AppendOnlyStore`` for append-only collections (calibration notes,
  engagement memories).

In-memory implementations are provided for testing. Production deployments
replace them with PostgreSQL-backed stores.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")
TVersion = TypeVar("TVersion")


# ---------------------------------------------------------------------------
# Versioned library store
# ---------------------------------------------------------------------------


class VersionedLibraryStore(ABC, Generic[TVersion]):
    """ABC for storing versioned library snapshots."""

    @abstractmethod
    def save_version(self, version: TVersion) -> None: ...

    @abstractmethod
    def get_version(self, version_id: UUID) -> TVersion | None: ...

    @abstractmethod
    def get_active(self) -> TVersion | None: ...

    @abstractmethod
    def set_active(self, version_id: UUID) -> None: ...

    @abstractmethod
    def list_versions(self) -> list[TVersion]: ...


class InMemoryVersionedLibraryStore(VersionedLibraryStore[TVersion]):
    """In-memory implementation for tests.

    Production replaces with PostgreSQL-backed store.
    """

    def __init__(self) -> None:
        self._versions: dict[UUID, TVersion] = {}
        self._active_id: UUID | None = None

    def save_version(self, version: TVersion) -> None:
        vid: UUID = getattr(version, "version_id")
        self._versions[vid] = version

    def get_version(self, version_id: UUID) -> TVersion | None:
        return self._versions.get(version_id)

    def get_active(self) -> TVersion | None:
        if self._active_id is None:
            return None
        return self._versions.get(self._active_id)

    def set_active(self, version_id: UUID) -> None:
        if version_id not in self._versions:
            msg = f"Version {version_id} not found."
            raise KeyError(msg)
        self._active_id = version_id

    def list_versions(self) -> list[TVersion]:
        return list(self._versions.values())


# ---------------------------------------------------------------------------
# Append-only store
# ---------------------------------------------------------------------------


class AppendOnlyStore(ABC, Generic[T]):
    """ABC for append-only stores (calibration notes, engagement memories)."""

    @abstractmethod
    def append(self, item: T) -> None: ...

    @abstractmethod
    def get(self, item_id: UUID) -> T | None: ...

    @abstractmethod
    def list_all(self) -> list[T]: ...


class InMemoryAppendOnlyStore(AppendOnlyStore[T]):
    """In-memory implementation for tests."""

    def __init__(self, id_field: str = "note_id") -> None:
        self._items: list[T] = []
        self._by_id: dict[UUID, T] = {}
        self._id_field = id_field

    def append(self, item: T) -> None:
        item_id: UUID = getattr(item, self._id_field)
        self._items.append(item)
        self._by_id[item_id] = item

    def get(self, item_id: UUID) -> T | None:
        return self._by_id.get(item_id)

    def list_all(self) -> list[T]:
        return list(self._items)
