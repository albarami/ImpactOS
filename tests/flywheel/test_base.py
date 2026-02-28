"""Tests for generic VersionedLibraryManager base (Task 3)."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.flywheel.base import VersionedLibraryManager
from src.flywheel.models import DraftStatus
from src.flywheel.stores import InMemoryVersionedLibraryStore
from src.models.common import ImpactOSBase, new_uuid7, utc_now


# ---------------------------------------------------------------------------
# Test fixtures: concrete test types for the generic manager
# ---------------------------------------------------------------------------


class _TestEntry(ImpactOSBase, frozen=True):
    """A single entry in a library version (e.g. a mapping row)."""

    entry_id: UUID
    value: str


class _TestDraft(ImpactOSBase, frozen=True):
    """A draft bundle awaiting publication."""

    draft_id: UUID
    status: DraftStatus
    entries: list[_TestEntry]


class _TestVersion(ImpactOSBase, frozen=True):
    """A published, immutable library version."""

    version_id: UUID
    version_number: int
    published_by: UUID
    entries: list[_TestEntry]


# ---------------------------------------------------------------------------
# Concrete test subclass of the generic manager
# ---------------------------------------------------------------------------


class _TestManager(VersionedLibraryManager[_TestEntry, _TestDraft, _TestVersion]):
    """Concrete manager for tests -- implements the two abstract methods."""

    def _make_version(
        self,
        draft: _TestDraft,
        version_number: int,
        published_by: UUID,
    ) -> _TestVersion:
        return _TestVersion(
            version_id=new_uuid7(),
            version_number=version_number,
            published_by=published_by,
            entries=draft.entries,
        )

    def _get_draft_status(self, draft: _TestDraft) -> DraftStatus:
        return draft.status


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_draft(
    status: DraftStatus = DraftStatus.DRAFT,
    entries: list[_TestEntry] | None = None,
) -> _TestDraft:
    if entries is None:
        entries = [_TestEntry(entry_id=new_uuid7(), value="item")]
    return _TestDraft(draft_id=new_uuid7(), status=status, entries=entries)


def _make_manager() -> _TestManager:
    store: InMemoryVersionedLibraryStore[_TestVersion] = (
        InMemoryVersionedLibraryStore()
    )
    return _TestManager(store=store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPublish:
    """VersionedLibraryManager.publish creates and activates versions."""

    def test_publish_creates_version_with_version_number_1(self) -> None:
        mgr = _make_manager()
        draft = _make_draft(status=DraftStatus.DRAFT)
        version = mgr.publish(draft, published_by=new_uuid7())
        assert version.version_number == 1

    def test_publish_sets_new_version_as_active(self) -> None:
        mgr = _make_manager()
        draft = _make_draft(status=DraftStatus.DRAFT)
        version = mgr.publish(draft, published_by=new_uuid7())
        assert mgr.get_active_version() == version

    def test_multiple_publishes_increment_version_numbers(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()
        v1 = mgr.publish(_make_draft(), published_by=publisher)
        v2 = mgr.publish(_make_draft(), published_by=publisher)
        v3 = mgr.publish(_make_draft(), published_by=publisher)
        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3

    def test_publish_with_review_status_succeeds(self) -> None:
        mgr = _make_manager()
        draft = _make_draft(status=DraftStatus.REVIEW)
        version = mgr.publish(draft, published_by=new_uuid7())
        assert version.version_number == 1

    def test_publish_with_rejected_draft_raises_value_error(self) -> None:
        mgr = _make_manager()
        draft = _make_draft(status=DraftStatus.REJECTED)
        with pytest.raises(ValueError, match="REJECTED"):
            mgr.publish(draft, published_by=new_uuid7())

    def test_publish_stores_correct_published_by(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()
        version = mgr.publish(_make_draft(), published_by=publisher)
        assert version.published_by == publisher


class TestGetActiveVersion:
    """VersionedLibraryManager.get_active_version retrieval."""

    def test_returns_none_when_nothing_published(self) -> None:
        mgr = _make_manager()
        assert mgr.get_active_version() is None

    def test_returns_latest_published(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()
        mgr.publish(_make_draft(), published_by=publisher)
        v2 = mgr.publish(_make_draft(), published_by=publisher)
        assert mgr.get_active_version() == v2


class TestGetVersion:
    """VersionedLibraryManager.get_version retrieves specific historical versions."""

    def test_returns_specific_version(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()
        v1 = mgr.publish(_make_draft(), published_by=publisher)
        mgr.publish(_make_draft(), published_by=publisher)
        assert mgr.get_version(v1.version_id) == v1

    def test_returns_none_for_unknown_id(self) -> None:
        mgr = _make_manager()
        assert mgr.get_version(new_uuid7()) is None


class TestListVersions:
    """VersionedLibraryManager.list_versions returns all published versions."""

    def test_empty_when_nothing_published(self) -> None:
        mgr = _make_manager()
        assert mgr.list_versions() == []

    def test_returns_all_published(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()
        v1 = mgr.publish(_make_draft(), published_by=publisher)
        v2 = mgr.publish(_make_draft(), published_by=publisher)
        versions = mgr.list_versions()
        assert len(versions) == 2
        assert v1 in versions
        assert v2 in versions
