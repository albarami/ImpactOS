"""Tests for MappingLibrary models and MappingLibraryManager (Tasks 4-5)."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.compiler.learning import LearningLoop, OverridePair
from src.flywheel.mapping_library import (
    MappingLibraryDraft,
    MappingLibraryManager,
    MappingLibraryVersion,
)
from src.flywheel.models import DraftStatus, ReuseScopeLevel
from src.flywheel.stores import InMemoryVersionedLibraryStore
from src.models.common import new_uuid7
from src.models.mapping import MappingLibraryEntry


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_entry(
    pattern: str = "concrete supply",
    sector_code: str = "S01",
    confidence: float = 0.8,
) -> MappingLibraryEntry:
    return MappingLibraryEntry(
        pattern=pattern,
        sector_code=sector_code,
        confidence=confidence,
    )


def _make_manager() -> MappingLibraryManager:
    store: InMemoryVersionedLibraryStore[MappingLibraryVersion] = (
        InMemoryVersionedLibraryStore()
    )
    return MappingLibraryManager(store=store)


def _make_override(
    line_item_text: str = "concrete supply",
    suggested_sector_code: str = "S01",
    final_sector_code: str = "S01",
) -> OverridePair:
    return OverridePair(
        engagement_id=new_uuid7(),
        line_item_id=new_uuid7(),
        line_item_text=line_item_text,
        suggested_sector_code=suggested_sector_code,
        final_sector_code=final_sector_code,
    )


# ---------------------------------------------------------------------------
# Task 4: MappingLibraryDraft model tests
# ---------------------------------------------------------------------------


class TestMappingLibraryDraft:
    """MappingLibraryDraft is a mutable draft with diff tracking."""

    def test_creates_with_default_draft_status(self) -> None:
        draft = MappingLibraryDraft()
        assert draft.status == DraftStatus.DRAFT

    def test_has_diff_fields(self) -> None:
        draft = MappingLibraryDraft()
        assert draft.changes_from_parent == []
        assert draft.added_entry_ids == []
        assert draft.removed_entry_ids == []
        assert draft.changed_entries == []

    def test_default_reuse_scope_is_workspace_only(self) -> None:
        draft = MappingLibraryDraft()
        assert draft.reuse_scope == ReuseScopeLevel.WORKSPACE_ONLY

    def test_entries_default_to_empty(self) -> None:
        draft = MappingLibraryDraft()
        assert draft.entries == []

    def test_parent_version_id_defaults_to_none(self) -> None:
        draft = MappingLibraryDraft()
        assert draft.parent_version_id is None


# ---------------------------------------------------------------------------
# Task 4: MappingLibraryVersion model tests
# ---------------------------------------------------------------------------


class TestMappingLibraryVersion:
    """MappingLibraryVersion is frozen and immutable."""

    def test_is_frozen_cannot_mutate(self) -> None:
        entry = _make_entry()
        version = MappingLibraryVersion(
            version_number=1,
            published_by=new_uuid7(),
            entries=[entry],
            entry_count=1,
        )
        with pytest.raises(Exception):
            version.version_number = 2  # type: ignore[misc]

    def test_entry_count_field_exists(self) -> None:
        version = MappingLibraryVersion(
            version_number=1,
            published_by=new_uuid7(),
            entry_count=5,
        )
        assert version.entry_count == 5

    def test_has_diff_tracking_fields(self) -> None:
        version = MappingLibraryVersion(
            version_number=1,
            published_by=new_uuid7(),
        )
        assert version.changes_from_parent == []
        assert version.added_entry_ids == []
        assert version.removed_entry_ids == []
        assert version.changed_entries == []

    def test_accuracy_at_publish_defaults_to_none(self) -> None:
        version = MappingLibraryVersion(
            version_number=1,
            published_by=new_uuid7(),
        )
        assert version.accuracy_at_publish is None


# ---------------------------------------------------------------------------
# Task 5: MappingLibraryManager tests
# ---------------------------------------------------------------------------


class TestMappingLibraryManagerBuildDraft:
    """MappingLibraryManager.build_draft creates drafts from base versions."""

    def test_build_draft_no_base_creates_empty_draft(self) -> None:
        mgr = _make_manager()
        draft = mgr.build_draft()
        assert draft.entries == []
        assert draft.status == DraftStatus.DRAFT
        assert draft.parent_version_id is None

    def test_build_draft_with_base_copies_entries(self) -> None:
        mgr = _make_manager()
        entry = _make_entry()
        draft1 = MappingLibraryDraft(entries=[entry])
        publisher = new_uuid7()
        v1 = mgr.publish(draft1, published_by=publisher)

        draft2 = mgr.build_draft(base_version_id=v1.version_id)
        assert len(draft2.entries) == 1
        assert draft2.entries[0].pattern == entry.pattern
        assert draft2.entries[0].sector_code == entry.sector_code
        assert draft2.parent_version_id == v1.version_id

    def test_build_draft_with_learning_loop_extracts_new_patterns(self) -> None:
        mgr = _make_manager()
        loop = LearningLoop()

        # Record overrides: same sector_code repeated >= min_frequency
        for _ in range(3):
            loop.record_override(_make_override(
                line_item_text="steel rebar supply",
                suggested_sector_code="S01",
                final_sector_code="S02",
            ))

        draft = mgr.build_draft(learning_loop=loop)
        # Should have extracted a new entry for sector S02
        assert len(draft.entries) >= 1
        sector_codes = [e.sector_code for e in draft.entries]
        assert "S02" in sector_codes

    def test_build_draft_with_learning_loop_updates_confidence_scores(self) -> None:
        mgr = _make_manager()
        entry = _make_entry(pattern="concrete supply", sector_code="S01", confidence=0.8)

        # Publish a base version with this entry
        draft1 = MappingLibraryDraft(entries=[entry])
        publisher = new_uuid7()
        v1 = mgr.publish(draft1, published_by=publisher)

        # Create learning loop with overrides matching S01
        loop = LearningLoop()
        # All correct: override accuracy = 1.0
        loop.record_override(_make_override(
            line_item_text="concrete supply",
            suggested_sector_code="S01",
            final_sector_code="S01",
        ))

        draft2 = mgr.build_draft(
            base_version_id=v1.version_id,
            learning_loop=loop,
        )
        # Confidence should be updated: (0.8 + 1.0) / 2 = 0.9
        assert len(draft2.entries) >= 1
        updated = [e for e in draft2.entries if e.sector_code == "S01"]
        assert len(updated) >= 1
        assert updated[0].confidence == pytest.approx(0.9)


class TestMappingLibraryManagerPublish:
    """MappingLibraryManager.publish creates immutable versions."""

    def test_publish_creates_immutable_version_sets_active(self) -> None:
        mgr = _make_manager()
        entry = _make_entry()
        draft = MappingLibraryDraft(entries=[entry])
        version = mgr.publish(draft, published_by=new_uuid7())

        assert version.version_number == 1
        assert mgr.get_active_version() == version
        assert version.entry_count == 1

    def test_multiple_publishes_increment_version_number(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()

        v1 = mgr.publish(MappingLibraryDraft(entries=[_make_entry()]), published_by=publisher)
        v2 = mgr.publish(MappingLibraryDraft(entries=[_make_entry()]), published_by=publisher)

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert mgr.get_active_version() == v2

    def test_old_versions_remain_accessible(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()

        v1 = mgr.publish(MappingLibraryDraft(entries=[_make_entry()]), published_by=publisher)
        mgr.publish(MappingLibraryDraft(entries=[_make_entry()]), published_by=publisher)

        retrieved = mgr.get_version(v1.version_id)
        assert retrieved is not None
        assert retrieved.version_number == 1

    def test_cannot_modify_published_version(self) -> None:
        mgr = _make_manager()
        version = mgr.publish(
            MappingLibraryDraft(entries=[_make_entry()]),
            published_by=new_uuid7(),
        )
        with pytest.raises(Exception):
            version.version_number = 99  # type: ignore[misc]
