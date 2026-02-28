"""Tests for FlywheelHealth metrics and FlywheelHealthService (Task 16).

Validates Amendment 10: backlog metrics and comprehensive health reporting
across all flywheel components.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.data.workforce.nationality_classification import (
    ClassificationOverride,
    NationalityTier,
)
from src.flywheel.assumption_library import (
    AssumptionDefault,
    AssumptionLibraryDraft,
    AssumptionLibraryManager,
)
from src.flywheel.calibration import CalibrationNote, CalibrationNoteStore
from src.flywheel.engagement_memory import EngagementMemory, EngagementMemoryStore
from src.flywheel.health import FlywheelHealth, FlywheelHealthService
from src.flywheel.mapping_library import MappingLibraryDraft, MappingLibraryManager
from src.flywheel.models import AssumptionValueType
from src.flywheel.scenario_patterns import ScenarioPatternLibrary
from src.flywheel.stores import InMemoryVersionedLibraryStore
from src.flywheel.workforce_refinement import WorkforceBridgeRefinement
from src.models.common import AssumptionType
from src.models.mapping import MappingLibraryEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_service() -> FlywheelHealthService:
    """Build a FlywheelHealthService with all empty in-memory stores."""
    mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
    assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
    pattern_lib = ScenarioPatternLibrary()
    calibration_store = CalibrationNoteStore()
    memory_store = EngagementMemoryStore()
    workforce_ref = WorkforceBridgeRefinement()

    return FlywheelHealthService(
        mapping_manager=mapping_mgr,
        assumption_manager=assumption_mgr,
        pattern_library=pattern_lib,
        calibration_store=calibration_store,
        memory_store=memory_store,
        workforce_refinement=workforce_ref,
    )


def _make_mapping_entry(**overrides) -> MappingLibraryEntry:
    """Build a minimal MappingLibraryEntry."""
    defaults = {
        "pattern": "cement",
        "sector_code": "F",
        "confidence": 0.9,
        "source": "test",
    }
    defaults.update(overrides)
    return MappingLibraryEntry(**defaults)


def _make_assumption_default(**overrides) -> AssumptionDefault:
    """Build a minimal AssumptionDefault."""
    defaults = {
        "assumption_type": AssumptionType.IMPORT_SHARE,
        "sector_code": "F",
        "name": "Test import share",
        "value_type": AssumptionValueType.NUMERIC,
        "default_numeric_value": 0.35,
        "unit": "ratio",
        "rationale": "test",
        "source": "test",
        "confidence": "medium",
    }
    defaults.update(overrides)
    return AssumptionDefault(**defaults)


# ---------------------------------------------------------------------------
# FlywheelHealth model tests
# ---------------------------------------------------------------------------


class TestFlywheelHealthModel:
    """FlywheelHealth schema must have all expected fields."""

    def test_has_standard_metric_fields(self) -> None:
        """FlywheelHealth has all standard metric fields."""
        health = FlywheelHealth()
        assert health.total_engagements == 0
        assert health.mapping_library_version == 0
        assert health.mapping_entry_count == 0
        assert health.mapping_accuracy is None
        assert health.assumption_default_count == 0
        assert health.assumption_library_version == 0
        assert health.scenario_pattern_count == 0
        assert health.calibration_note_count == 0
        assert health.engagement_memory_count == 0
        assert health.workforce_coverage_pct == 0.0

    def test_has_backlog_metrics(self) -> None:
        """FlywheelHealth has all Amendment 10 backlog metric fields."""
        health = FlywheelHealth()
        assert health.override_backlog_count == 0
        assert health.avg_days_since_last_publication == 0.0
        assert health.draft_count_pending_review == 0
        assert health.pct_entries_assumed_vs_calibrated == 0.0
        assert health.pct_shared_knowledge_sanitized == 0.0
        assert health.last_publication is None


# ---------------------------------------------------------------------------
# FlywheelHealthService tests
# ---------------------------------------------------------------------------


class TestFlywheelHealthServiceEmpty:
    """Service with empty state should return all-zero metrics."""

    def test_compute_health_empty_state(self) -> None:
        """compute_health() with no data returns all zeros/None."""
        svc = _build_service()
        health = svc.compute_health()
        assert isinstance(health, FlywheelHealth)
        assert health.mapping_library_version == 0
        assert health.mapping_entry_count == 0
        assert health.mapping_accuracy is None
        assert health.assumption_default_count == 0
        assert health.assumption_library_version == 0
        assert health.scenario_pattern_count == 0
        assert health.calibration_note_count == 0
        assert health.engagement_memory_count == 0
        assert health.workforce_coverage_pct == 0.0
        assert health.last_publication is None


class TestFlywheelHealthServiceWithData:
    """Service correctly aggregates metrics from populated components."""

    def test_after_publishing_mapping_version(self) -> None:
        """compute_health() reports mapping metrics after publishing."""
        mapping_store = InMemoryVersionedLibraryStore()
        mapping_mgr = MappingLibraryManager(store=mapping_store)
        assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        # Publish a mapping version with 2 entries
        entry1 = _make_mapping_entry(pattern="cement", sector_code="F")
        entry2 = _make_mapping_entry(pattern="steel", sector_code="C")
        draft = MappingLibraryDraft(entries=[entry1, entry2])
        user_id = uuid4()
        mapping_mgr.publish(draft, published_by=user_id)

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        assert health.mapping_library_version == 1
        assert health.mapping_entry_count == 2
        assert health.last_publication is not None

    def test_after_publishing_assumption_version(self) -> None:
        """compute_health() reports assumption metrics after publishing."""
        mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
        assumption_store = InMemoryVersionedLibraryStore()
        assumption_mgr = AssumptionLibraryManager(store=assumption_store)
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        # Publish an assumption version with 3 defaults
        defaults = [_make_assumption_default(name=f"default_{i}") for i in range(3)]
        draft = AssumptionLibraryDraft(defaults=defaults)
        user_id = uuid4()
        assumption_mgr.publish(draft, published_by=user_id)

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        assert health.assumption_library_version == 1
        assert health.assumption_default_count == 3
        assert health.last_publication is not None

    def test_with_scenario_patterns(self) -> None:
        """compute_health() reports scenario pattern count."""
        mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
        assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        # Record two distinct patterns (different project types to avoid merge)
        pattern_lib.record_engagement_pattern(
            engagement_id=uuid4(),
            scenario_spec_id=uuid4(),
            project_type="logistics_zone",
            sector_shares={"F": 0.6, "C": 0.4},
        )
        pattern_lib.record_engagement_pattern(
            engagement_id=uuid4(),
            scenario_spec_id=uuid4(),
            project_type="housing",
            sector_shares={"F": 0.8, "G": 0.2},
        )

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        assert health.scenario_pattern_count == 2

    def test_with_calibration_notes(self) -> None:
        """compute_health() reports calibration note count."""
        mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
        assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        ws_id = uuid4()
        user_id = uuid4()
        note = CalibrationNote(
            observation="Construction multiplier overstated",
            likely_cause="Outdated coefficients",
            metric_affected="employment",
            direction="overstate",
            created_by=user_id,
            workspace_id=ws_id,
        )
        calibration_store.append(note)

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        assert health.calibration_note_count == 1

    def test_with_engagement_memories(self) -> None:
        """compute_health() reports engagement memory count."""
        mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
        assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        ws_id = uuid4()
        user_id = uuid4()
        eng_id = uuid4()
        memory = EngagementMemory(
            engagement_id=eng_id,
            category="challenge",
            description="Client challenged import share for steel",
            created_by=user_id,
            workspace_id=ws_id,
        )
        memory_store.append(memory)

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        assert health.engagement_memory_count == 1

    def test_workforce_coverage_pct_computed(self) -> None:
        """compute_health() computes workforce_coverage_pct from refinement."""
        mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
        assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        # Record overrides to create coverage
        eng_id = uuid4()
        overrides = [
            ClassificationOverride(
                sector_code="F",
                occupation_code="OCC1",
                original_tier=NationalityTier.EXPAT_RELIANT,
                override_tier=NationalityTier.SAUDI_TRAINABLE,
                overridden_by="analyst",
                engagement_id=str(eng_id),
                rationale="test",
                timestamp="2024-01-15T10:00:00Z",
            ),
            ClassificationOverride(
                sector_code="C",
                occupation_code="OCC2",
                original_tier=NationalityTier.EXPAT_RELIANT,
                override_tier=NationalityTier.SAUDI_READY,
                overridden_by="analyst",
                engagement_id=str(eng_id),
                rationale="test",
                timestamp="2024-01-15T10:00:00Z",
            ),
        ]
        workforce_ref.record_engagement_overrides(eng_id, overrides)

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        # total_cells == engagement_calibrated_cells when we have no base comparison
        # So coverage = 100%
        assert health.workforce_coverage_pct == 100.0

    def test_workforce_coverage_zero_when_no_overrides(self) -> None:
        """workforce_coverage_pct is 0.0 when no overrides exist."""
        svc = _build_service()
        health = svc.compute_health()
        assert health.workforce_coverage_pct == 0.0

    def test_last_publication_takes_latest(self) -> None:
        """last_publication should be the latest published_at from any component."""
        mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
        assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        user_id = uuid4()

        # Publish mapping version first
        entry = _make_mapping_entry()
        mapping_draft = MappingLibraryDraft(entries=[entry])
        mapping_mgr.publish(mapping_draft, published_by=user_id)

        # Publish assumption version second (will be later)
        defaults = [_make_assumption_default()]
        assumption_draft = AssumptionLibraryDraft(defaults=defaults)
        assumption_mgr.publish(assumption_draft, published_by=user_id)

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        assert health.last_publication is not None

        # last_publication should be >= both published_at values
        mapping_pub = mapping_mgr.get_active_version().published_at
        assumption_pub = assumption_mgr.get_active_version().published_at
        assert health.last_publication >= mapping_pub
        assert health.last_publication >= assumption_pub

    def test_avg_days_since_last_publication_computed(self) -> None:
        """avg_days_since_last_publication is > 0 when last_publication is set."""
        mapping_mgr = MappingLibraryManager(store=InMemoryVersionedLibraryStore())
        assumption_mgr = AssumptionLibraryManager(store=InMemoryVersionedLibraryStore())
        pattern_lib = ScenarioPatternLibrary()
        calibration_store = CalibrationNoteStore()
        memory_store = EngagementMemoryStore()
        workforce_ref = WorkforceBridgeRefinement()

        user_id = uuid4()

        # Publish a mapping version so last_publication is set
        entry = _make_mapping_entry()
        mapping_draft = MappingLibraryDraft(entries=[entry])
        mapping_mgr.publish(mapping_draft, published_by=user_id)

        svc = FlywheelHealthService(
            mapping_manager=mapping_mgr,
            assumption_manager=assumption_mgr,
            pattern_library=pattern_lib,
            calibration_store=calibration_store,
            memory_store=memory_store,
            workforce_refinement=workforce_ref,
        )
        health = svc.compute_health()
        assert health.last_publication is not None
        # Published just now, so avg_days should be very small (>= 0)
        assert health.avg_days_since_last_publication >= 0.0

    def test_avg_days_since_last_publication_zero_when_no_publication(self) -> None:
        """avg_days_since_last_publication is 0.0 when no publication exists."""
        svc = _build_service()
        health = svc.compute_health()
        assert health.last_publication is None
        assert health.avg_days_since_last_publication == 0.0
