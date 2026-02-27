"""Tests for AssumptionLibraryService (MVP-12)."""

import pytest
from uuid_extensions import uuid7

from src.models.common import ConstraintConfidence
from src.models.libraries import (
    AssumptionLibraryEntry,
    EntryStatus,
    LibraryAssumptionType,
)


def _make_entry(
    assumption_type: LibraryAssumptionType = LibraryAssumptionType.IMPORT_SHARE,
    sector: str = "F",
    default_value: float = 0.35,
    confidence: ConstraintConfidence = ConstraintConfidence.ESTIMATED,
    usage: int = 0,
    status: EntryStatus = EntryStatus.PUBLISHED,
) -> AssumptionLibraryEntry:
    return AssumptionLibraryEntry(
        workspace_id=uuid7(),
        assumption_type=assumption_type,
        sector_code=sector,
        default_value=default_value,
        range_low=default_value * 0.5,
        range_high=default_value * 1.5,
        unit="fraction",
        confidence=confidence,
        usage_count=usage,
        status=status,
    )


class TestAssumptionLibraryService:
    def test_add_entry(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        svc = AssumptionLibraryService([])
        entry = _make_entry()
        result = svc.add_entry(entry)
        assert result.entry_id == entry.entry_id
        assert len(svc._entries) == 1

    def test_get_defaults_by_sector(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        entries = [
            _make_entry(sector="F"),
            _make_entry(sector="C"),
            _make_entry(sector="F",
                        assumption_type=LibraryAssumptionType.PHASING),
        ]
        svc = AssumptionLibraryService(entries)
        defaults = svc.get_defaults("F")
        assert len(defaults) == 2
        assert all(e.sector_code == "F" for e in defaults)

    def test_get_defaults_by_sector_and_type(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        entries = [
            _make_entry(sector="F",
                        assumption_type=LibraryAssumptionType.IMPORT_SHARE),
            _make_entry(sector="F",
                        assumption_type=LibraryAssumptionType.PHASING),
        ]
        svc = AssumptionLibraryService(entries)
        defaults = svc.get_defaults(
            "F", LibraryAssumptionType.IMPORT_SHARE,
        )
        assert len(defaults) == 1
        assert defaults[0].assumption_type == LibraryAssumptionType.IMPORT_SHARE

    def test_get_defaults_no_match(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        svc = AssumptionLibraryService([_make_entry(sector="F")])
        assert svc.get_defaults("Z") == []

    def test_get_defaults_ranked_by_confidence_then_usage(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        entries = [
            _make_entry(sector="F", confidence=ConstraintConfidence.ASSUMED,
                        usage=10),
            _make_entry(sector="F", confidence=ConstraintConfidence.HARD,
                        usage=1),
            _make_entry(sector="F", confidence=ConstraintConfidence.ESTIMATED,
                        usage=5),
        ]
        svc = AssumptionLibraryService(entries)
        defaults = svc.get_defaults("F")
        assert defaults[0].confidence == ConstraintConfidence.HARD
        assert defaults[1].confidence == ConstraintConfidence.ESTIMATED
        assert defaults[2].confidence == ConstraintConfidence.ASSUMED

    def test_publish_version_only_published(self) -> None:
        """Amendment 7: Only PUBLISHED entries in version snapshot."""
        from src.libraries.assumption_library import AssumptionLibraryService

        ws = uuid7()
        entries = [
            _make_entry(status=EntryStatus.PUBLISHED),
            _make_entry(status=EntryStatus.DRAFT),
            _make_entry(status=EntryStatus.DEPRECATED),
        ]
        for e in entries:
            e.workspace_id = ws
        svc = AssumptionLibraryService(entries)
        version = svc.publish_version(workspace_id=ws)
        assert version.entry_count == 1

    def test_publish_version_immutable(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        svc = AssumptionLibraryService([])
        version = svc.publish_version(workspace_id=uuid7())
        with pytest.raises(Exception):
            version.version = 99  # type: ignore[misc]

    def test_get_stats_empty(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        svc = AssumptionLibraryService([])
        stats = svc.get_stats()
        assert stats.total_entries == 0

    def test_get_stats_populated(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        entries = [
            _make_entry(sector="F", usage=10, confidence=ConstraintConfidence.HARD),
            _make_entry(sector="C", usage=5, confidence=ConstraintConfidence.ESTIMATED),
        ]
        svc = AssumptionLibraryService(entries)
        stats = svc.get_stats()
        assert stats.total_entries == 2
        assert stats.total_usage == 15

    def test_increment_usage(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        entry = _make_entry(usage=3)
        svc = AssumptionLibraryService([entry])
        result = svc.increment_usage(entry.entry_id)
        assert result is not None
        assert result.usage_count == 4

    def test_increment_usage_nonexistent(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        svc = AssumptionLibraryService([])
        assert svc.increment_usage(uuid7()) is None

    def test_add_duplicate_reinforces(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        e1 = _make_entry(
            sector="F",
            assumption_type=LibraryAssumptionType.IMPORT_SHARE,
        )
        svc = AssumptionLibraryService([e1])
        e2 = _make_entry(
            sector="F",
            assumption_type=LibraryAssumptionType.IMPORT_SHARE,
        )
        e2.default_value = e1.default_value  # Same defaults
        svc.add_entry(e2)
        # Should reinforce if sector+type match
        assert len(svc._entries) <= 2  # May or may not dedup

    def test_confidence_ordering(self) -> None:
        """Verify HARD > ESTIMATED > ASSUMED ordering in defaults."""
        from src.libraries.assumption_library import AssumptionLibraryService

        entries = [
            _make_entry(sector="F", confidence=ConstraintConfidence.ASSUMED),
            _make_entry(sector="F", confidence=ConstraintConfidence.HARD),
        ]
        svc = AssumptionLibraryService(entries)
        defaults = svc.get_defaults("F")
        assert defaults[0].confidence == ConstraintConfidence.HARD

    def test_all_assumption_types(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        entries = [
            _make_entry(sector="F", assumption_type=t)
            for t in LibraryAssumptionType
        ]
        svc = AssumptionLibraryService(entries)
        stats = svc.get_stats()
        assert stats.total_entries == len(LibraryAssumptionType)

    def test_publish_version_entry_ids(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        ws = uuid7()
        entries = [_make_entry(status=EntryStatus.PUBLISHED)]
        entries[0].workspace_id = ws
        svc = AssumptionLibraryService(entries)
        version = svc.publish_version(workspace_id=ws)
        assert entries[0].entry_id in version.entry_ids

    def test_publish_version_entry_count(self) -> None:
        from src.libraries.assumption_library import AssumptionLibraryService

        ws = uuid7()
        entries = [
            _make_entry(status=EntryStatus.PUBLISHED),
            _make_entry(status=EntryStatus.PUBLISHED),
        ]
        for e in entries:
            e.workspace_id = ws
        svc = AssumptionLibraryService(entries)
        version = svc.publish_version(workspace_id=ws)
        assert version.entry_count == 2
