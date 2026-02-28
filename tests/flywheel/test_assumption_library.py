"""Tests for AssumptionLibrary models, manager, and seed defaults (Tasks 7-8)."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.flywheel.assumption_library import (
    AssumptionDefault,
    AssumptionLibraryDraft,
    AssumptionLibraryManager,
    AssumptionLibraryVersion,
    build_seed_defaults,
)
from src.flywheel.models import AssumptionValueType, DraftStatus, ReuseScopeLevel
from src.flywheel.stores import InMemoryVersionedLibraryStore
from src.models.common import AssumptionType, new_uuid7


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_numeric_default(
    assumption_type: AssumptionType = AssumptionType.IMPORT_SHARE,
    sector_code: str | None = "F",
    name: str = "Construction import share",
    default_numeric_value: float = 0.35,
    default_numeric_range: tuple[float, float] = (0.25, 0.50),
    unit: str = "ratio",
    source: str = "benchmark_initial",
    confidence: str = "medium",
) -> AssumptionDefault:
    return AssumptionDefault(
        assumption_type=assumption_type,
        sector_code=sector_code,
        name=name,
        value_type=AssumptionValueType.NUMERIC,
        default_numeric_value=default_numeric_value,
        default_numeric_range=default_numeric_range,
        unit=unit,
        rationale="Test rationale",
        source=source,
        confidence=confidence,
    )


def _make_categorical_default(
    assumption_type: AssumptionType = AssumptionType.PHASING,
    sector_code: str | None = None,
    name: str = "Default phasing profile",
    default_text_value: str = "even",
    allowed_values: list[str] | None = None,
    unit: str = "profile",
    source: str = "Expert",
    confidence: str = "medium",
) -> AssumptionDefault:
    return AssumptionDefault(
        assumption_type=assumption_type,
        sector_code=sector_code,
        name=name,
        value_type=AssumptionValueType.CATEGORICAL,
        default_text_value=default_text_value,
        allowed_values=allowed_values or ["front", "even", "back"],
        unit=unit,
        rationale="Test rationale",
        source=source,
        confidence=confidence,
    )


def _make_manager() -> AssumptionLibraryManager:
    store: InMemoryVersionedLibraryStore[AssumptionLibraryVersion] = (
        InMemoryVersionedLibraryStore()
    )
    return AssumptionLibraryManager(store=store)


# ---------------------------------------------------------------------------
# Task 7: AssumptionDefault model tests
# ---------------------------------------------------------------------------


class TestAssumptionDefault:
    """AssumptionDefault supports numeric and categorical value types."""

    def test_numeric_type_has_value_and_range_text_is_none(self) -> None:
        ad = _make_numeric_default()
        assert ad.value_type == AssumptionValueType.NUMERIC
        assert ad.default_numeric_value == 0.35
        assert ad.default_numeric_range == (0.25, 0.50)
        assert ad.default_text_value is None
        assert ad.allowed_values is None

    def test_categorical_type_has_text_value_and_allowed_values_numeric_is_none(
        self,
    ) -> None:
        ad = _make_categorical_default()
        assert ad.value_type == AssumptionValueType.CATEGORICAL
        assert ad.default_text_value == "even"
        assert ad.allowed_values == ["front", "even", "back"]
        assert ad.default_numeric_value is None
        assert ad.default_numeric_range is None

    def test_reuses_assumption_type_from_common(self) -> None:
        ad = _make_numeric_default(assumption_type=AssumptionType.JOBS_COEFF)
        assert ad.assumption_type == AssumptionType.JOBS_COEFF
        assert isinstance(ad.assumption_type, AssumptionType)

    def test_default_reuse_scope_is_global_internal(self) -> None:
        ad = _make_numeric_default()
        assert ad.reuse_scope == ReuseScopeLevel.GLOBAL_INTERNAL

    def test_usage_count_defaults_to_zero(self) -> None:
        ad = _make_numeric_default()
        assert ad.usage_count == 0

    def test_workspace_id_defaults_to_none(self) -> None:
        ad = _make_numeric_default()
        assert ad.workspace_id is None

    def test_source_engagement_id_defaults_to_none(self) -> None:
        ad = _make_numeric_default()
        assert ad.source_engagement_id is None


# ---------------------------------------------------------------------------
# Task 7: AssumptionLibraryDraft model tests
# ---------------------------------------------------------------------------


class TestAssumptionLibraryDraft:
    """AssumptionLibraryDraft is mutable with default DRAFT status."""

    def test_default_status_is_draft(self) -> None:
        draft = AssumptionLibraryDraft()
        assert draft.status == DraftStatus.DRAFT

    def test_has_diff_fields(self) -> None:
        draft = AssumptionLibraryDraft()
        assert draft.changes_from_parent == []
        assert draft.added_entry_ids == []
        assert draft.removed_entry_ids == []
        assert draft.changed_entries == []

    def test_defaults_list_empty(self) -> None:
        draft = AssumptionLibraryDraft()
        assert draft.defaults == []


# ---------------------------------------------------------------------------
# Task 7: AssumptionLibraryVersion model tests
# ---------------------------------------------------------------------------


class TestAssumptionLibraryVersion:
    """AssumptionLibraryVersion is frozen (immutable)."""

    def test_is_frozen_cannot_mutate(self) -> None:
        version = AssumptionLibraryVersion(
            version_number=1,
            published_by=new_uuid7(),
            defaults=[_make_numeric_default()],
            default_count=1,
        )
        with pytest.raises(Exception):
            version.version_number = 2  # type: ignore[misc]

    def test_default_count_field_exists(self) -> None:
        version = AssumptionLibraryVersion(
            version_number=1,
            published_by=new_uuid7(),
            default_count=5,
        )
        assert version.default_count == 5


# ---------------------------------------------------------------------------
# Task 7: AssumptionLibraryManager tests
# ---------------------------------------------------------------------------


class TestAssumptionLibraryManagerGetDefaultsForSector:
    """get_defaults_for_sector returns sector-specific + economy-wide defaults."""

    def test_returns_sector_specific_and_economy_wide(self) -> None:
        mgr = _make_manager()
        construction = _make_numeric_default(sector_code="F", name="Construction import share")
        economy_wide = _make_numeric_default(
            sector_code=None,
            name="Economy-wide import share",
            default_numeric_value=0.30,
        )
        manufacturing = _make_numeric_default(
            sector_code="C",
            name="Manufacturing import share",
        )
        draft = AssumptionLibraryDraft(
            defaults=[construction, economy_wide, manufacturing],
        )
        publisher = new_uuid7()
        mgr.publish(draft, published_by=publisher)

        result = mgr.get_defaults_for_sector("F")
        names = [d.name for d in result]
        assert "Construction import share" in names
        assert "Economy-wide import share" in names
        assert "Manufacturing import share" not in names

    def test_filters_by_assumption_type(self) -> None:
        mgr = _make_manager()
        import_share = _make_numeric_default(
            assumption_type=AssumptionType.IMPORT_SHARE,
            sector_code="F",
            name="Construction import share",
        )
        jobs_coeff = _make_numeric_default(
            assumption_type=AssumptionType.JOBS_COEFF,
            sector_code="F",
            name="Construction employment coefficient",
            default_numeric_value=18.5,
            unit="jobs_per_million_SAR",
        )
        draft = AssumptionLibraryDraft(defaults=[import_share, jobs_coeff])
        mgr.publish(draft, published_by=new_uuid7())

        result = mgr.get_defaults_for_sector("F", AssumptionType.IMPORT_SHARE)
        assert len(result) == 1
        assert result[0].name == "Construction import share"

    def test_no_matching_sector_returns_economy_wide_only(self) -> None:
        mgr = _make_manager()
        economy_wide = _make_numeric_default(
            sector_code=None,
            name="Economy-wide import share",
        )
        construction = _make_numeric_default(
            sector_code="F",
            name="Construction import share",
        )
        draft = AssumptionLibraryDraft(defaults=[economy_wide, construction])
        mgr.publish(draft, published_by=new_uuid7())

        result = mgr.get_defaults_for_sector("Z")
        assert len(result) == 1
        assert result[0].name == "Economy-wide import share"


class TestAssumptionLibraryManagerBuildDraft:
    """build_draft creates drafts from base versions."""

    def test_build_draft_no_base_creates_empty_draft(self) -> None:
        mgr = _make_manager()
        draft = mgr.build_draft()
        assert draft.defaults == []
        assert draft.status == DraftStatus.DRAFT
        assert draft.parent_version_id is None

    def test_build_draft_with_base_copies_defaults_from_parent(self) -> None:
        mgr = _make_manager()
        entry = _make_numeric_default()
        draft1 = AssumptionLibraryDraft(defaults=[entry])
        publisher = new_uuid7()
        v1 = mgr.publish(draft1, published_by=publisher)

        draft2 = mgr.build_draft(base_version_id=v1.version_id)
        assert len(draft2.defaults) == 1
        assert draft2.defaults[0].name == entry.name
        assert draft2.parent_version_id == v1.version_id


class TestAssumptionLibraryManagerPublish:
    """publish creates immutable versions and increments version numbers."""

    def test_publish_creates_version_and_sets_active(self) -> None:
        mgr = _make_manager()
        entry = _make_numeric_default()
        draft = AssumptionLibraryDraft(defaults=[entry])
        version = mgr.publish(draft, published_by=new_uuid7())

        assert version.version_number == 1
        assert mgr.get_active_version() == version
        assert version.default_count == 1

    def test_version_number_increments(self) -> None:
        mgr = _make_manager()
        publisher = new_uuid7()

        v1 = mgr.publish(
            AssumptionLibraryDraft(defaults=[_make_numeric_default()]),
            published_by=publisher,
        )
        v2 = mgr.publish(
            AssumptionLibraryDraft(defaults=[_make_numeric_default()]),
            published_by=publisher,
        )

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert mgr.get_active_version() == v2


# ---------------------------------------------------------------------------
# Task 8: Seed defaults tests
# ---------------------------------------------------------------------------


class TestBuildSeedDefaults:
    """build_seed_defaults produces 7 valid defaults from D-3/D-4 data."""

    def test_returns_7_defaults(self) -> None:
        seeds = build_seed_defaults()
        assert len(seeds) == 7

    def test_all_defaults_are_valid_assumption_default_instances(self) -> None:
        seeds = build_seed_defaults()
        for seed in seeds:
            assert isinstance(seed, AssumptionDefault)

    def test_phasing_is_categorical_with_allowed_values(self) -> None:
        seeds = build_seed_defaults()
        phasing = [s for s in seeds if s.assumption_type == AssumptionType.PHASING]
        assert len(phasing) == 1
        p = phasing[0]
        assert p.value_type == AssumptionValueType.CATEGORICAL
        assert p.default_text_value == "even"
        assert p.allowed_values == ["front", "even", "back"]
        assert p.default_numeric_value is None

    def test_import_share_construction_has_correct_range(self) -> None:
        seeds = build_seed_defaults()
        construction_imports = [
            s
            for s in seeds
            if s.assumption_type == AssumptionType.IMPORT_SHARE
            and s.sector_code == "F"
        ]
        assert len(construction_imports) == 1
        ci = construction_imports[0]
        assert ci.default_numeric_value == 0.35
        assert ci.default_numeric_range == (0.25, 0.50)

    def test_all_seeds_have_medium_confidence(self) -> None:
        seeds = build_seed_defaults()
        for seed in seeds:
            assert seed.confidence == "medium"

    def test_numeric_seeds_have_numeric_value_type(self) -> None:
        seeds = build_seed_defaults()
        non_phasing = [
            s for s in seeds if s.assumption_type != AssumptionType.PHASING
        ]
        for seed in non_phasing:
            assert seed.value_type == AssumptionValueType.NUMERIC
            assert seed.default_numeric_value is not None
            assert seed.default_numeric_range is not None

    def test_economy_wide_defaults_have_none_sector_code(self) -> None:
        seeds = build_seed_defaults()
        economy_wide = [
            s
            for s in seeds
            if s.name in ("Economy-wide import share", "Default phasing profile", "Default GDP deflator")
        ]
        for ew in economy_wide:
            assert ew.sector_code is None
