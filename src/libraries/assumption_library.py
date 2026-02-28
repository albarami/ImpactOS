"""Assumption Library Service — MVP-12.

Stores sector-level default assumptions with ranges.
Ranked by confidence (HARD > ESTIMATED > ASSUMED) then usage count.

Amendment 6: evidence_refs on entries.
Amendment 7: Entry status filtering for published versions.
"""

from collections import Counter
from uuid import UUID

from src.models.common import ConstraintConfidence, utc_now
from src.models.libraries import (
    AssumptionLibraryEntry,
    AssumptionLibraryVersion,
    EntryStatus,
    LibraryAssumptionType,
    LibraryStats,
)

# Confidence ordering for ranking
_CONFIDENCE_RANK: dict[ConstraintConfidence, int] = {
    ConstraintConfidence.HARD: 0,
    ConstraintConfidence.ESTIMATED: 1,
    ConstraintConfidence.ASSUMED: 2,
}


class AssumptionLibraryService:
    """In-memory assumption library service."""

    def __init__(
        self, entries: list[AssumptionLibraryEntry],
    ) -> None:
        self._entries: list[AssumptionLibraryEntry] = list(entries)

    def add_entry(
        self, entry: AssumptionLibraryEntry,
    ) -> AssumptionLibraryEntry:
        """Add entry to the library."""
        self._entries.append(entry)
        return entry

    def get_defaults(
        self,
        sector_code: str,
        assumption_type: LibraryAssumptionType | None = None,
    ) -> list[AssumptionLibraryEntry]:
        """Get defaults for a sector, optionally filtered by type.

        Ranked by confidence (HARD first) then usage_count descending.
        """
        results = [
            e for e in self._entries
            if e.sector_code == sector_code
            and (assumption_type is None or e.assumption_type == assumption_type)
        ]
        results.sort(
            key=lambda e: (
                _CONFIDENCE_RANK.get(e.confidence, 99),
                -e.usage_count,
            ),
        )
        return results

    def publish_version(
        self,
        *,
        workspace_id: UUID,
        published_by: UUID | None = None,
    ) -> AssumptionLibraryVersion:
        """Snapshot PUBLISHED entries into immutable version (Amendment 7)."""
        published = [
            e for e in self._entries
            if e.status == EntryStatus.PUBLISHED
        ]
        return AssumptionLibraryVersion(
            workspace_id=workspace_id,
            entry_ids=[e.entry_id for e in published],
            entry_count=len(published),
            published_by=published_by,
        )

    def get_stats(self) -> LibraryStats:
        """Compute aggregate statistics."""
        if not self._entries:
            return LibraryStats()

        total_usage = sum(e.usage_count for e in self._entries)
        # Map ConstraintConfidence to numeric for averaging
        conf_map = {
            ConstraintConfidence.HARD: 1.0,
            ConstraintConfidence.ESTIMATED: 0.6,
            ConstraintConfidence.ASSUMED: 0.3,
        }
        avg_conf = sum(
            conf_map.get(e.confidence, 0.3) for e in self._entries
        ) / len(self._entries)

        sector_counts: Counter[str] = Counter(
            e.sector_code for e in self._entries
        )
        top_sectors = [s for s, _ in sector_counts.most_common(10)]

        return LibraryStats(
            total_entries=len(self._entries),
            total_usage=total_usage,
            avg_confidence=round(avg_conf, 4),
            top_sectors=top_sectors,
        )

    def increment_usage(
        self, entry_id: UUID,
    ) -> AssumptionLibraryEntry | None:
        """Increment usage_count and last_used_at (Amendment 2)."""
        for i, entry in enumerate(self._entries):
            if entry.entry_id == entry_id:
                updated = entry.model_copy(
                    update={
                        "usage_count": entry.usage_count + 1,
                        "last_used_at": utc_now(),
                    },
                )
                self._entries[i] = updated
                return updated
        return None
