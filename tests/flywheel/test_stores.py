"""Tests for flywheel store ABCs and InMemory implementations (Task 2)."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.flywheel.stores import (
    AppendOnlyStore,
    InMemoryAppendOnlyStore,
    InMemoryVersionedLibraryStore,
    VersionedLibraryStore,
)
from src.models.common import ImpactOSBase, new_uuid7


# ---------------------------------------------------------------------------
# Test fixtures: simple frozen Pydantic models
# ---------------------------------------------------------------------------


class _TestVersion(ImpactOSBase, frozen=True):
    """Minimal versioned item for testing VersionedLibraryStore."""

    version_id: UUID
    name: str


class _TestItem(ImpactOSBase, frozen=True):
    """Minimal item for testing AppendOnlyStore."""

    note_id: UUID
    text: str


# ---------------------------------------------------------------------------
# InMemoryVersionedLibraryStore tests
# ---------------------------------------------------------------------------


class TestInMemoryVersionedLibraryStore:
    """InMemoryVersionedLibraryStore CRUD and active-version management."""

    def test_save_and_get_version(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        vid = new_uuid7()
        version = _TestVersion(version_id=vid, name="v1")
        store.save_version(version)
        assert store.get_version(vid) == version

    def test_get_nonexistent_returns_none(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        assert store.get_version(new_uuid7()) is None

    def test_get_active_initially_none(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        assert store.get_active() is None

    def test_set_active_and_get_active(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        vid = new_uuid7()
        version = _TestVersion(version_id=vid, name="v1")
        store.save_version(version)
        store.set_active(vid)
        assert store.get_active() == version

    def test_set_active_nonexistent_raises_key_error(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        with pytest.raises(KeyError):
            store.set_active(new_uuid7())

    def test_list_versions_empty(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        assert store.list_versions() == []

    def test_list_versions_multiple(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        v1 = _TestVersion(version_id=new_uuid7(), name="v1")
        v2 = _TestVersion(version_id=new_uuid7(), name="v2")
        store.save_version(v1)
        store.save_version(v2)
        versions = store.list_versions()
        assert len(versions) == 2
        assert v1 in versions
        assert v2 in versions

    def test_set_active_replaces_previous(self) -> None:
        store: InMemoryVersionedLibraryStore[_TestVersion] = (
            InMemoryVersionedLibraryStore()
        )
        v1 = _TestVersion(version_id=new_uuid7(), name="v1")
        v2 = _TestVersion(version_id=new_uuid7(), name="v2")
        store.save_version(v1)
        store.save_version(v2)
        store.set_active(v1.version_id)
        assert store.get_active() == v1
        store.set_active(v2.version_id)
        assert store.get_active() == v2

    def test_is_subclass_of_abc(self) -> None:
        assert issubclass(InMemoryVersionedLibraryStore, VersionedLibraryStore)


# ---------------------------------------------------------------------------
# InMemoryAppendOnlyStore tests
# ---------------------------------------------------------------------------


class TestInMemoryAppendOnlyStore:
    """InMemoryAppendOnlyStore append, get, and list operations."""

    def test_append_and_get(self) -> None:
        store: InMemoryAppendOnlyStore[_TestItem] = InMemoryAppendOnlyStore()
        nid = new_uuid7()
        item = _TestItem(note_id=nid, text="hello")
        store.append(item)
        assert store.get(nid) == item

    def test_get_nonexistent_returns_none(self) -> None:
        store: InMemoryAppendOnlyStore[_TestItem] = InMemoryAppendOnlyStore()
        assert store.get(new_uuid7()) is None

    def test_list_all_empty(self) -> None:
        store: InMemoryAppendOnlyStore[_TestItem] = InMemoryAppendOnlyStore()
        assert store.list_all() == []

    def test_list_all_preserves_order(self) -> None:
        store: InMemoryAppendOnlyStore[_TestItem] = InMemoryAppendOnlyStore()
        items = [_TestItem(note_id=new_uuid7(), text=f"item-{i}") for i in range(3)]
        for item in items:
            store.append(item)
        assert store.list_all() == items

    def test_custom_id_field(self) -> None:
        """AppendOnlyStore can use a custom id field name."""

        class _CustomIdItem(ImpactOSBase, frozen=True):
            custom_id: UUID
            value: int

        store: InMemoryAppendOnlyStore[_CustomIdItem] = InMemoryAppendOnlyStore(
            id_field="custom_id"
        )
        cid = new_uuid7()
        item = _CustomIdItem(custom_id=cid, value=42)
        store.append(item)
        assert store.get(cid) == item

    def test_is_subclass_of_abc(self) -> None:
        assert issubclass(InMemoryAppendOnlyStore, AppendOnlyStore)
