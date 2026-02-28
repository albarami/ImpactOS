"""Mapping Library — versioned mapping patterns for the Knowledge Flywheel.

Provides:
- ``MappingLibraryDraft``: mutable draft being assembled (Amendment 2)
- ``MappingLibraryVersion``: frozen, immutable, referenced by RunSnapshot
- ``MappingLibraryManager``: manages publish/release workflow, integrates
  with LearningLoop for continuous improvement

Per tech spec Section 9.6 and MVP-12 design doc.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.compiler.learning import LearningLoop, OverridePair
from src.flywheel.base import VersionedLibraryManager
from src.flywheel.models import DraftStatus, ReuseScopeLevel
from src.flywheel.stores import VersionedLibraryStore
from src.models.common import ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now
from src.models.mapping import MappingLibraryEntry


# ---------------------------------------------------------------------------
# Draft model (mutable, being assembled)
# ---------------------------------------------------------------------------


class MappingLibraryDraft(ImpactOSBase):
    """Mutable draft of a mapping library version (Amendment 2).

    Tracks changes relative to a parent version for audit purposes.
    """

    draft_id: UUIDv7 = Field(default_factory=new_uuid7)
    parent_version_id: UUID | None = None
    entries: list[MappingLibraryEntry] = Field(default_factory=list)
    status: DraftStatus = DraftStatus.DRAFT
    changes_from_parent: list[str] = Field(default_factory=list)
    added_entry_ids: list[UUID] = Field(default_factory=list)
    removed_entry_ids: list[UUID] = Field(default_factory=list)
    changed_entries: list[dict] = Field(default_factory=list)
    workspace_id: UUID | None = None
    reuse_scope: ReuseScopeLevel = ReuseScopeLevel.WORKSPACE_ONLY


# ---------------------------------------------------------------------------
# Version model (frozen, immutable)
# ---------------------------------------------------------------------------


class MappingLibraryVersion(ImpactOSBase, frozen=True):
    """Immutable published mapping library version.

    Referenced by RunSnapshot to ensure reproducibility.
    """

    version_id: UUIDv7 = Field(default_factory=new_uuid7)
    version_number: int
    published_at: UTCTimestamp = Field(default_factory=utc_now)
    published_by: UUID
    entries: list[MappingLibraryEntry] = Field(default_factory=list)
    entry_count: int = 0
    parent_version_id: UUID | None = None
    changes_from_parent: list[str] = Field(default_factory=list)
    added_entry_ids: list[UUID] = Field(default_factory=list)
    removed_entry_ids: list[UUID] = Field(default_factory=list)
    changed_entries: list[dict] = Field(default_factory=list)
    total_overrides_ingested: int = 0
    accuracy_at_publish: float | None = None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class MappingLibraryManager(
    VersionedLibraryManager[
        MappingLibraryEntry,
        MappingLibraryDraft,
        MappingLibraryVersion,
    ]
):
    """Manages mapping library versions with publish/release workflow.

    Integrates with ``LearningLoop`` to incorporate analyst overrides
    into new library versions.
    """

    def build_draft(
        self,
        base_version_id: UUID | None = None,
        include_overrides_since: datetime | None = None,
        learning_loop: LearningLoop | None = None,
    ) -> MappingLibraryDraft:
        """Build a new draft version incorporating recent overrides.

        Parameters
        ----------
        base_version_id:
            If provided, copy entries from this published version.
        include_overrides_since:
            Timestamp filter for overrides (reserved for future use).
        learning_loop:
            If provided, extract new patterns and update confidences
            from recorded analyst overrides.

        Returns
        -------
        MappingLibraryDraft
            A new mutable draft ready for review/publication.
        """
        entries: list[MappingLibraryEntry] = []
        parent_version_id: UUID | None = None

        # Start with entries from base version if provided
        if base_version_id is not None:
            base_version = self.get_version(base_version_id)
            if base_version is not None:
                entries = list(base_version.entries)
                parent_version_id = base_version_id

        added_entry_ids: list[UUID] = []
        changes_from_parent: list[str] = []
        changed_entries: list[dict] = []

        # Integrate learning loop if provided
        if learning_loop is not None:
            overrides = learning_loop.get_overrides(since=include_overrides_since)

            # Update confidence scores on existing entries
            if entries:
                updated_entries = learning_loop.update_confidence_scores(
                    overrides, entries
                )
                # Track changes
                for old_entry, new_entry in zip(entries, updated_entries):
                    if old_entry.confidence != new_entry.confidence:
                        changed_entries.append({
                            "entry_id": str(new_entry.entry_id),
                            "field": "confidence",
                            "old_value": old_entry.confidence,
                            "new_value": new_entry.confidence,
                        })
                        changes_from_parent.append(
                            f"Updated confidence for {new_entry.pattern}: "
                            f"{old_entry.confidence:.3f} -> {new_entry.confidence:.3f}"
                        )
                entries = updated_entries

            # Extract new patterns from overrides
            new_patterns = learning_loop.extract_new_patterns(
                overrides, existing_library=entries
            )
            for new_entry in new_patterns:
                entries.append(new_entry)
                added_entry_ids.append(new_entry.entry_id)
                changes_from_parent.append(
                    f"Added new pattern: {new_entry.pattern} -> {new_entry.sector_code}"
                )

        return MappingLibraryDraft(
            parent_version_id=parent_version_id,
            entries=entries,
            status=DraftStatus.DRAFT,
            changes_from_parent=changes_from_parent,
            added_entry_ids=added_entry_ids,
            changed_entries=changed_entries,
        )

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def _make_version(
        self,
        draft: MappingLibraryDraft,
        version_number: int,
        published_by: UUID,
    ) -> MappingLibraryVersion:
        """Build a frozen MappingLibraryVersion from a draft."""
        return MappingLibraryVersion(
            version_number=version_number,
            published_by=published_by,
            entries=draft.entries,
            entry_count=len(draft.entries),
            parent_version_id=draft.parent_version_id,
            changes_from_parent=draft.changes_from_parent,
            added_entry_ids=draft.added_entry_ids,
            removed_entry_ids=draft.removed_entry_ids,
            changed_entries=draft.changed_entries,
        )

    def _get_draft_status(self, draft: MappingLibraryDraft) -> DraftStatus:
        """Extract the DraftStatus from a MappingLibraryDraft."""
        return draft.status
