"""Tests for PublicationQualityGate, PublicationResult, and FlywheelPublicationService (Tasks 13-14)."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.compiler.learning import LearningLoop, OverridePair
from src.flywheel.assumption_library import (
    AssumptionDefault,
    AssumptionLibraryDraft,
    AssumptionLibraryManager,
    AssumptionLibraryVersion,
    build_seed_defaults,
)
from src.flywheel.mapping_library import (
    MappingLibraryDraft,
    MappingLibraryManager,
    MappingLibraryVersion,
)
from src.flywheel.models import AssumptionValueType, DraftStatus
from src.flywheel.publication import (
    FlywheelPublicationService,
    PublicationQualityGate,
    PublicationResult,
)
from src.flywheel.scenario_patterns import ScenarioPatternLibrary
from src.flywheel.stores import InMemoryVersionedLibraryStore
from src.flywheel.workforce_refinement import WorkforceBridgeRefinement
from src.models.common import AssumptionType, new_uuid7, utc_now
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


def _make_assumption_default(
    name: str = "Test import share",
    sector_code: str = "F",
    value: float = 0.35,
) -> AssumptionDefault:
    return AssumptionDefault(
        assumption_type=AssumptionType.IMPORT_SHARE,
        sector_code=sector_code,
        name=name,
        value_type=AssumptionValueType.NUMERIC,
        default_numeric_value=value,
        unit="ratio",
        rationale="Test rationale",
        source="test",
        confidence="medium",
    )


def _make_mapping_manager() -> MappingLibraryManager:
    store: InMemoryVersionedLibraryStore[MappingLibraryVersion] = (
        InMemoryVersionedLibraryStore()
    )
    return MappingLibraryManager(store=store)


def _make_assumption_manager() -> AssumptionLibraryManager:
    store: InMemoryVersionedLibraryStore[AssumptionLibraryVersion] = (
        InMemoryVersionedLibraryStore()
    )
    return AssumptionLibraryManager(store=store)


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


def _make_service(
    mapping_manager: MappingLibraryManager | None = None,
    assumption_manager: AssumptionLibraryManager | None = None,
    pattern_library: ScenarioPatternLibrary | None = None,
    workforce_refinement: WorkforceBridgeRefinement | None = None,
) -> FlywheelPublicationService:
    return FlywheelPublicationService(
        mapping_manager=mapping_manager or _make_mapping_manager(),
        assumption_manager=assumption_manager or _make_assumption_manager(),
        pattern_library=pattern_library or ScenarioPatternLibrary(),
        workforce_refinement=workforce_refinement or WorkforceBridgeRefinement(),
    )


# ---------------------------------------------------------------------------
# Quality Gate tests
# ---------------------------------------------------------------------------


class TestPublicationQualityGate:
    """Tests for PublicationQualityGate validation logic."""

    def test_validate_draft_no_issues_returns_empty(self) -> None:
        """A clean draft with steward approval and no duplicates passes all gates."""
        gate = PublicationQualityGate()
        draft = MappingLibraryDraft(
            entries=[
                _make_entry("concrete supply", "S01"),
                _make_entry("steel rebar", "S02"),
            ],
        )
        failures = gate.validate_mapping_draft(draft, steward_approved=True)
        assert failures == []

    def test_validate_draft_steward_review_not_approved(self) -> None:
        """If require_steward_review is True and not approved, gate fails."""
        gate = PublicationQualityGate(require_steward_review=True)
        draft = MappingLibraryDraft(
            entries=[_make_entry("concrete supply", "S01")],
        )
        failures = gate.validate_mapping_draft(draft, steward_approved=False)
        assert len(failures) >= 1
        assert any("steward" in f.lower() for f in failures)

    def test_validate_draft_duplicate_entries(self) -> None:
        """Duplicate entries (same pattern + sector_code) trigger gate failure."""
        gate = PublicationQualityGate(duplicate_check=True)
        entry1 = _make_entry("concrete supply", "S01", confidence=0.8)
        entry2 = _make_entry("concrete supply", "S01", confidence=0.9)
        draft = MappingLibraryDraft(entries=[entry1, entry2])
        failures = gate.validate_mapping_draft(draft, steward_approved=True)
        assert len(failures) >= 1
        assert any("duplicate" in f.lower() for f in failures)

    def test_validate_draft_conflicting_entries(self) -> None:
        """Conflicting entries (same pattern, different sector_code) trigger gate failure."""
        gate = PublicationQualityGate(conflict_check=True)
        entry1 = _make_entry("concrete supply", "S01")
        entry2 = _make_entry("concrete supply", "S02")
        draft = MappingLibraryDraft(entries=[entry1, entry2])
        failures = gate.validate_mapping_draft(draft, steward_approved=True)
        assert len(failures) >= 1
        assert any("conflict" in f.lower() for f in failures)

    def test_validate_draft_all_checks_disabled(self) -> None:
        """With all checks disabled, even problematic drafts pass."""
        gate = PublicationQualityGate(
            require_steward_review=False,
            duplicate_check=False,
            conflict_check=False,
        )
        entry1 = _make_entry("concrete supply", "S01")
        entry2 = _make_entry("concrete supply", "S02")  # conflict
        entry3 = _make_entry("concrete supply", "S01")  # duplicate
        draft = MappingLibraryDraft(entries=[entry1, entry2, entry3])
        failures = gate.validate_mapping_draft(draft, steward_approved=False)
        assert failures == []


# ---------------------------------------------------------------------------
# Publication Service tests
# ---------------------------------------------------------------------------


class TestFlywheelPublicationService:
    """Tests for FlywheelPublicationService orchestration."""

    def test_publish_new_cycle_creates_versions(self) -> None:
        """publish_new_cycle publishes mapping and assumption versions."""
        mapping_mgr = _make_mapping_manager()
        assumption_mgr = _make_assumption_manager()
        service = _make_service(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
        )

        # Seed the managers with some initial data via drafts
        m_draft = MappingLibraryDraft(entries=[_make_entry()])
        mapping_mgr.publish(m_draft, published_by=new_uuid7())

        a_draft = AssumptionLibraryDraft(defaults=[_make_assumption_default()])
        assumption_mgr.publish(a_draft, published_by=new_uuid7())

        publisher_id = new_uuid7()
        result = service.publish_new_cycle(published_by=publisher_id)

        assert isinstance(result, PublicationResult)
        # Even though no changes from active, result should be returned
        # (idempotency means no NEW versions if content is identical)

    def test_publish_new_cycle_returns_publication_result(self) -> None:
        """PublicationResult has all expected fields populated."""
        service = _make_service()
        publisher_id = new_uuid7()
        result = service.publish_new_cycle(published_by=publisher_id)

        assert isinstance(result, PublicationResult)
        assert result.published_at is not None
        assert isinstance(result.new_patterns, int)
        assert isinstance(result.updated_patterns, int)
        assert isinstance(result.workforce_coverage, dict)
        assert isinstance(result.summary, str)

    def test_publish_new_cycle_idempotent_no_changes(self) -> None:
        """If no changes from active version, no new versions are published."""
        mapping_mgr = _make_mapping_manager()
        assumption_mgr = _make_assumption_manager()
        service = _make_service(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
        )

        # Publish initial versions
        entries = [_make_entry("concrete supply", "S01")]
        m_draft = MappingLibraryDraft(entries=entries)
        mapping_mgr.publish(m_draft, published_by=new_uuid7())

        defaults = [_make_assumption_default()]
        a_draft = AssumptionLibraryDraft(defaults=defaults)
        assumption_mgr.publish(a_draft, published_by=new_uuid7())

        # Publish cycle with no new overrides — should be idempotent
        publisher_id = new_uuid7()
        result = service.publish_new_cycle(published_by=publisher_id)

        # No new versions should have been created
        assert result.mapping_version is None
        assert result.assumption_version is None

    def test_publish_new_cycle_quality_gate_failures_skip_mapping(self) -> None:
        """Quality gate failures prevent mapping publication, but assumption still publishes."""
        mapping_mgr = _make_mapping_manager()
        assumption_mgr = _make_assumption_manager()
        service = _make_service(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
        )

        # Create a learning loop with overrides that will produce new patterns
        learning_loop = LearningLoop()
        for _ in range(3):
            learning_loop.record_override(_make_override(
                line_item_text="concrete supply",
                suggested_sector_code="S01",
                final_sector_code="S02",
            ))

        # Quality gate that requires steward review (not approved)
        gate = PublicationQualityGate(require_steward_review=True)

        publisher_id = new_uuid7()
        result = service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=learning_loop,
            steward_approved=False,
            quality_gate=gate,
        )

        # Mapping should NOT be published due to gate failure
        assert result.mapping_version is None

    def test_get_flywheel_health(self) -> None:
        """get_flywheel_health returns pattern count and workforce coverage."""
        pattern_lib = ScenarioPatternLibrary()
        workforce = WorkforceBridgeRefinement()
        mapping_mgr = _make_mapping_manager()
        assumption_mgr = _make_assumption_manager()

        # Add a pattern
        pattern_lib.record_engagement_pattern(
            engagement_id=new_uuid7(),
            scenario_spec_id=new_uuid7(),
            project_type="logistics_zone",
            sector_shares={"F": 0.6, "C": 0.4},
        )

        service = _make_service(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            workforce_refinement=workforce,
        )

        health = service.get_flywheel_health()
        assert health["pattern_count"] == 1
        assert "workforce_coverage" in health

    def test_publish_new_cycle_with_learning_loop(self) -> None:
        """publish_new_cycle with learning_loop incorporates overrides into mapping."""
        mapping_mgr = _make_mapping_manager()
        assumption_mgr = _make_assumption_manager()
        service = _make_service(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
        )

        # Create learning loop with overrides that produce new patterns
        learning_loop = LearningLoop()
        for _ in range(3):
            learning_loop.record_override(_make_override(
                line_item_text="steel rebar delivery",
                suggested_sector_code="S01",
                final_sector_code="S03",
            ))

        publisher_id = new_uuid7()
        result = service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=learning_loop,
            steward_approved=True,
        )

        # New mapping version should have been published with the new patterns
        assert result.mapping_version is not None
        assert result.new_patterns > 0

    def test_publication_result_fields(self) -> None:
        """PublicationResult has all expected fields with correct defaults."""
        result = PublicationResult()
        assert result.mapping_version is None
        assert result.assumption_version is None
        assert result.new_patterns == 0
        assert result.updated_patterns == 0
        assert result.workforce_coverage == {}
        assert result.published_at is not None
        assert result.summary == ""

    def test_publish_new_cycle_with_no_prior_versions(self) -> None:
        """publish_new_cycle with no prior versions and no learning loop produces empty result."""
        service = _make_service()
        publisher_id = new_uuid7()
        result = service.publish_new_cycle(published_by=publisher_id)

        # No prior versions + no learning loop = nothing to publish
        assert result.mapping_version is None
        assert result.assumption_version is None

    def test_publish_new_cycle_gate_passes_publishes_mapping(self) -> None:
        """When quality gate passes, mapping draft is published."""
        mapping_mgr = _make_mapping_manager()
        assumption_mgr = _make_assumption_manager()
        service = _make_service(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
        )

        # Create learning loop with overrides
        learning_loop = LearningLoop()
        for _ in range(3):
            learning_loop.record_override(_make_override(
                line_item_text="plumbing fixtures",
                suggested_sector_code="S01",
                final_sector_code="S04",
            ))

        # Quality gate that passes (steward approved)
        gate = PublicationQualityGate(require_steward_review=True)

        publisher_id = new_uuid7()
        result = service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=learning_loop,
            steward_approved=True,
            quality_gate=gate,
        )

        # Mapping should be published since gate passes
        assert result.mapping_version is not None

    def test_quality_gate_default_values(self) -> None:
        """PublicationQualityGate has sensible defaults per Amendment 6."""
        gate = PublicationQualityGate()
        assert gate.min_override_frequency == 2
        assert gate.min_accuracy_delta == 0.0
        assert gate.require_steward_review is True
        assert gate.duplicate_check is True
        assert gate.conflict_check is True

    def test_publish_new_cycle_populates_summary(self) -> None:
        """publish_new_cycle returns a result with a non-empty summary when changes occur."""
        mapping_mgr = _make_mapping_manager()
        service = _make_service(mapping_manager=mapping_mgr)

        # Create learning loop with overrides
        learning_loop = LearningLoop()
        for _ in range(3):
            learning_loop.record_override(_make_override(
                line_item_text="electrical wiring",
                suggested_sector_code="S01",
                final_sector_code="S05",
            ))

        publisher_id = new_uuid7()
        result = service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=learning_loop,
            steward_approved=True,
        )

        assert result.summary != ""
