"""Tests for Knowledge Flywheel Pydantic models (MVP-12).

Schema tests for: LibraryAssumptionType, MappingLibraryEntry,
MappingLibraryVersion, AssumptionLibraryEntry, AssumptionLibraryVersion,
ScenarioPattern, LibraryStats, OverrideAccuracyReport.

All 8 amendments enforced.
"""

import pytest
from uuid import UUID
from uuid_extensions import uuid7

from src.models.common import ConstraintConfidence


# ---------------------------------------------------------------------------
# LibraryAssumptionType enum
# ---------------------------------------------------------------------------


class TestLibraryAssumptionType:
    def test_all_values_present(self) -> None:
        from src.models.libraries import LibraryAssumptionType

        expected = {
            "IMPORT_SHARE", "PHASING", "DEFLATOR", "WAGE_PROXY",
            "CAPACITY_CAP", "JOBS_COEFF", "LOCAL_CONTENT", "OTHER",
        }
        actual = {v.value for v in LibraryAssumptionType}
        assert actual == expected

    def test_superset_of_common_assumption_type(self) -> None:
        from src.models.common import AssumptionType
        from src.models.libraries import LibraryAssumptionType

        for member in AssumptionType:
            assert member.value in {v.value for v in LibraryAssumptionType}


# ---------------------------------------------------------------------------
# EntryStatus
# ---------------------------------------------------------------------------


class TestEntryStatus:
    def test_all_values(self) -> None:
        from src.models.libraries import EntryStatus

        assert set(EntryStatus) == {
            EntryStatus.DRAFT, EntryStatus.PUBLISHED, EntryStatus.DEPRECATED,
        }

    def test_default_is_draft(self) -> None:
        from src.models.libraries import EntryStatus

        assert EntryStatus.DRAFT == "DRAFT"


# ---------------------------------------------------------------------------
# MappingLibraryEntry
# ---------------------------------------------------------------------------


class TestMappingLibraryEntry:
    def test_valid_construction(self) -> None:
        from src.models.libraries import MappingLibraryEntry

        ws = uuid7()
        entry = MappingLibraryEntry(
            workspace_id=ws,
            pattern="concrete works",
            sector_code="F",
            confidence=0.95,
        )
        assert isinstance(entry.entry_id, UUID)
        assert entry.workspace_id == ws
        assert entry.pattern == "concrete works"
        assert entry.sector_code == "F"
        assert entry.confidence == 0.95

    def test_defaults(self) -> None:
        from src.models.libraries import EntryStatus, MappingLibraryEntry

        entry = MappingLibraryEntry(
            workspace_id=uuid7(),
            pattern="test",
            sector_code="A",
            confidence=0.5,
        )
        assert entry.usage_count == 0
        assert entry.source_engagement_id is None
        assert entry.last_used_at is None
        assert entry.tags == []
        assert entry.created_by is None
        assert entry.status == EntryStatus.DRAFT
        assert entry.created_at is not None

    def test_confidence_bounds_low(self) -> None:
        from src.models.libraries import MappingLibraryEntry

        with pytest.raises(Exception):
            MappingLibraryEntry(
                workspace_id=uuid7(),
                pattern="test",
                sector_code="A",
                confidence=-0.1,
            )

    def test_confidence_bounds_high(self) -> None:
        from src.models.libraries import MappingLibraryEntry

        with pytest.raises(Exception):
            MappingLibraryEntry(
                workspace_id=uuid7(),
                pattern="test",
                sector_code="A",
                confidence=1.1,
            )

    def test_pattern_min_length(self) -> None:
        from src.models.libraries import MappingLibraryEntry

        with pytest.raises(Exception):
            MappingLibraryEntry(
                workspace_id=uuid7(),
                pattern="",
                sector_code="A",
                confidence=0.5,
            )

    def test_serialization_roundtrip(self) -> None:
        from src.models.libraries import MappingLibraryEntry

        entry = MappingLibraryEntry(
            workspace_id=uuid7(),
            pattern="steel reinforcement",
            sector_code="F",
            confidence=0.9,
            tags=["construction", "steel"],
        )
        data = entry.model_dump(mode="json")
        restored = MappingLibraryEntry.model_validate(data)
        assert restored.pattern == entry.pattern
        assert restored.tags == ["construction", "steel"]

    def test_tags_with_values(self) -> None:
        from src.models.libraries import MappingLibraryEntry

        entry = MappingLibraryEntry(
            workspace_id=uuid7(),
            pattern="IT consulting",
            sector_code="J",
            confidence=0.8,
            tags=["IT", "consulting"],
        )
        assert entry.tags == ["IT", "consulting"]


# ---------------------------------------------------------------------------
# MappingLibraryVersion
# ---------------------------------------------------------------------------


class TestMappingLibraryVersion:
    def test_valid_construction(self) -> None:
        from src.models.libraries import MappingLibraryVersion

        ids = [uuid7(), uuid7()]
        v = MappingLibraryVersion(
            workspace_id=uuid7(),
            version=1,
            entry_ids=ids,
            entry_count=2,
        )
        assert v.version == 1
        assert v.entry_count == 2
        assert len(v.entry_ids) == 2

    def test_frozen_immutability(self) -> None:
        from src.models.libraries import MappingLibraryVersion

        v = MappingLibraryVersion(
            workspace_id=uuid7(),
            version=1,
            entry_ids=[],
            entry_count=0,
        )
        with pytest.raises(Exception):
            v.version = 2  # type: ignore[misc]

    def test_default_version_is_1(self) -> None:
        from src.models.libraries import MappingLibraryVersion

        v = MappingLibraryVersion(workspace_id=uuid7())
        assert v.version == 1
        assert v.entry_count == 0
        assert v.entry_ids == []

    def test_published_by_nullable(self) -> None:
        from src.models.libraries import MappingLibraryVersion

        v = MappingLibraryVersion(workspace_id=uuid7(), published_by=uuid7())
        assert v.published_by is not None


# ---------------------------------------------------------------------------
# AssumptionLibraryEntry
# ---------------------------------------------------------------------------


class TestAssumptionLibraryEntry:
    def test_valid_construction(self) -> None:
        from src.models.libraries import (
            AssumptionLibraryEntry,
            LibraryAssumptionType,
        )

        entry = AssumptionLibraryEntry(
            workspace_id=uuid7(),
            assumption_type=LibraryAssumptionType.IMPORT_SHARE,
            sector_code="F",
            default_value=0.35,
            range_low=0.20,
            range_high=0.50,
            unit="fraction",
        )
        assert entry.default_value == 0.35
        assert entry.range_low == 0.20
        assert entry.range_high == 0.50

    def test_range_validation_ok(self) -> None:
        from src.models.libraries import (
            AssumptionLibraryEntry,
            LibraryAssumptionType,
        )

        entry = AssumptionLibraryEntry(
            workspace_id=uuid7(),
            assumption_type=LibraryAssumptionType.DEFLATOR,
            sector_code="C",
            default_value=1.0,
            range_low=1.0,
            range_high=1.0,  # equal is OK
            unit="ratio",
        )
        assert entry.range_low == entry.range_high

    def test_range_violation_raises(self) -> None:
        from src.models.libraries import (
            AssumptionLibraryEntry,
            LibraryAssumptionType,
        )

        with pytest.raises(ValueError, match="range_high"):
            AssumptionLibraryEntry(
                workspace_id=uuid7(),
                assumption_type=LibraryAssumptionType.PHASING,
                sector_code="A",
                default_value=0.5,
                range_low=0.8,
                range_high=0.2,
                unit="fraction",
            )

    def test_confidence_default_assumed(self) -> None:
        from src.models.libraries import (
            AssumptionLibraryEntry,
            LibraryAssumptionType,
        )

        entry = AssumptionLibraryEntry(
            workspace_id=uuid7(),
            assumption_type=LibraryAssumptionType.JOBS_COEFF,
            sector_code="F",
            default_value=10.0,
            range_low=5.0,
            range_high=15.0,
            unit="jobs/M SAR",
        )
        assert entry.confidence == ConstraintConfidence.ASSUMED

    def test_evidence_refs_default_empty(self) -> None:
        """Amendment 6: evidence_refs on AssumptionLibraryEntry."""
        from src.models.libraries import (
            AssumptionLibraryEntry,
            LibraryAssumptionType,
        )

        entry = AssumptionLibraryEntry(
            workspace_id=uuid7(),
            assumption_type=LibraryAssumptionType.LOCAL_CONTENT,
            sector_code="F",
            default_value=0.40,
            range_low=0.30,
            range_high=0.50,
            unit="fraction",
        )
        assert entry.evidence_refs == []

    def test_evidence_refs_with_values(self) -> None:
        """Amendment 6: evidence_refs populated."""
        from src.models.libraries import (
            AssumptionLibraryEntry,
            LibraryAssumptionType,
        )

        ref1, ref2 = uuid7(), uuid7()
        entry = AssumptionLibraryEntry(
            workspace_id=uuid7(),
            assumption_type=LibraryAssumptionType.IMPORT_SHARE,
            sector_code="F",
            default_value=0.35,
            range_low=0.20,
            range_high=0.50,
            unit="fraction",
            evidence_refs=[ref1, ref2],
        )
        assert len(entry.evidence_refs) == 2

    def test_status_default_draft(self) -> None:
        """Amendment 7: entry status defaults to DRAFT."""
        from src.models.libraries import (
            AssumptionLibraryEntry,
            EntryStatus,
            LibraryAssumptionType,
        )

        entry = AssumptionLibraryEntry(
            workspace_id=uuid7(),
            assumption_type=LibraryAssumptionType.IMPORT_SHARE,
            sector_code="F",
            default_value=0.35,
            range_low=0.20,
            range_high=0.50,
            unit="fraction",
        )
        assert entry.status == EntryStatus.DRAFT

    def test_serialization_roundtrip(self) -> None:
        from src.models.libraries import (
            AssumptionLibraryEntry,
            LibraryAssumptionType,
        )

        entry = AssumptionLibraryEntry(
            workspace_id=uuid7(),
            assumption_type=LibraryAssumptionType.OTHER,
            sector_code="G",
            default_value=0.1,
            range_low=0.0,
            range_high=0.3,
            unit="index",
            justification="Expert opinion",
            source="engagement",
        )
        data = entry.model_dump(mode="json")
        restored = AssumptionLibraryEntry.model_validate(data)
        assert restored.assumption_type == LibraryAssumptionType.OTHER


# ---------------------------------------------------------------------------
# AssumptionLibraryVersion
# ---------------------------------------------------------------------------


class TestAssumptionLibraryVersion:
    def test_valid_construction(self) -> None:
        from src.models.libraries import AssumptionLibraryVersion

        v = AssumptionLibraryVersion(
            workspace_id=uuid7(),
            version=3,
            entry_ids=[uuid7()],
            entry_count=1,
        )
        assert v.version == 3

    def test_frozen_immutability(self) -> None:
        from src.models.libraries import AssumptionLibraryVersion

        v = AssumptionLibraryVersion(workspace_id=uuid7())
        with pytest.raises(Exception):
            v.version = 5  # type: ignore[misc]

    def test_default_version_is_1(self) -> None:
        from src.models.libraries import AssumptionLibraryVersion

        v = AssumptionLibraryVersion(workspace_id=uuid7())
        assert v.version == 1
        assert v.entry_count == 0


# ---------------------------------------------------------------------------
# ScenarioPattern
# ---------------------------------------------------------------------------


class TestScenarioPattern:
    def test_valid_construction(self) -> None:
        from src.models.libraries import ScenarioPattern

        p = ScenarioPattern(
            workspace_id=uuid7(),
            name="Mega-project construction",
            description="Standard pattern for large construction projects",
            sector_focus=["F", "C"],
            typical_shock_types=["FINAL_DEMAND"],
        )
        assert p.name == "Mega-project construction"
        assert p.sector_focus == ["F", "C"]

    def test_defaults(self) -> None:
        from src.models.libraries import ScenarioPattern

        p = ScenarioPattern(
            workspace_id=uuid7(),
            name="Test pattern",
        )
        assert p.description == ""
        assert p.sector_focus == []
        assert p.typical_shock_types == []
        assert p.typical_assumptions == []
        assert p.recommended_sensitivities == []
        assert p.recommended_contrarian_angles == []
        assert p.source_engagement_ids == []
        assert p.usage_count == 0
        assert p.tags == []
        assert p.created_by is None

    def test_name_min_length(self) -> None:
        from src.models.libraries import ScenarioPattern

        with pytest.raises(Exception):
            ScenarioPattern(workspace_id=uuid7(), name="")

    def test_serialization_roundtrip(self) -> None:
        from src.models.libraries import ScenarioPattern

        p = ScenarioPattern(
            workspace_id=uuid7(),
            name="Infrastructure PPP",
            sector_focus=["F", "H"],
            tags=["infrastructure", "PPP"],
            source_engagement_ids=[uuid7()],
        )
        data = p.model_dump(mode="json")
        restored = ScenarioPattern.model_validate(data)
        assert restored.tags == ["infrastructure", "PPP"]

    def test_usage_count_ge_0(self) -> None:
        from src.models.libraries import ScenarioPattern

        with pytest.raises(Exception):
            ScenarioPattern(
                workspace_id=uuid7(),
                name="Test",
                usage_count=-1,
            )


# ---------------------------------------------------------------------------
# LibraryStats
# ---------------------------------------------------------------------------


class TestLibraryStats:
    def test_valid_construction(self) -> None:
        from src.models.libraries import LibraryStats

        s = LibraryStats(
            total_entries=100,
            total_versions=5,
            total_usage=500,
            avg_confidence=0.85,
            top_sectors=["F", "C", "J"],
        )
        assert s.total_entries == 100
        assert s.top_sectors == ["F", "C", "J"]

    def test_defaults_all_zero(self) -> None:
        from src.models.libraries import LibraryStats

        s = LibraryStats()
        assert s.total_entries == 0
        assert s.total_versions == 0
        assert s.total_usage == 0
        assert s.avg_confidence == 0.0
        assert s.top_sectors == []

    def test_avg_confidence_bounds(self) -> None:
        from src.models.libraries import LibraryStats

        with pytest.raises(Exception):
            LibraryStats(avg_confidence=1.5)


# ---------------------------------------------------------------------------
# OverrideAccuracyReport
# ---------------------------------------------------------------------------


class TestOverrideAccuracyReport:
    def test_valid_construction(self) -> None:
        from src.models.libraries import OverrideAccuracyReport

        r = OverrideAccuracyReport(
            total_suggestions=100,
            accepted_count=80,
            overridden_count=20,
            accuracy_pct=0.80,
        )
        assert r.accuracy_pct == 0.80

    def test_defaults(self) -> None:
        from src.models.libraries import OverrideAccuracyReport

        r = OverrideAccuracyReport()
        assert r.total_suggestions == 0
        assert r.accepted_count == 0
        assert r.overridden_count == 0
        assert r.accuracy_pct == 0.0
        assert r.by_sector == {}
        assert r.high_confidence_overrides == []

    def test_accuracy_pct_bounds(self) -> None:
        from src.models.libraries import OverrideAccuracyReport

        with pytest.raises(Exception):
            OverrideAccuracyReport(accuracy_pct=1.5)

    def test_by_sector_structure(self) -> None:
        from src.models.libraries import OverrideAccuracyReport

        r = OverrideAccuracyReport(
            by_sector={
                "F": {"total": 50, "correct": 40, "accuracy": 0.80},
                "C": {"total": 30, "correct": 25, "accuracy": 0.83},
            },
        )
        assert "F" in r.by_sector
        assert r.by_sector["F"]["accuracy"] == 0.80

    def test_high_confidence_overrides_list(self) -> None:
        from src.models.libraries import OverrideAccuracyReport

        r = OverrideAccuracyReport(
            high_confidence_overrides=[
                {"pattern": "concrete", "final_sector": "F", "count": 5},
            ],
        )
        assert len(r.high_confidence_overrides) == 1
