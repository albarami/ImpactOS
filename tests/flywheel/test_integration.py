"""End-to-end integration tests for the Knowledge Flywheel (Tasks 17-18).

Validates the full flywheel lifecycle across all components: mapping library,
assumption library, scenario patterns, calibration notes, engagement memory,
workforce refinement, publication service, and health metrics.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.compiler.learning import LearningLoop, OverridePair
from src.data.workforce.nationality_classification import (
    ClassificationOverride,
    NationalityClassification,
    NationalityClassificationSet,
    NationalityTier,
)
from src.data.workforce.unit_registry import QualityConfidence
from src.flywheel.assumption_library import (
    AssumptionDefault,
    AssumptionLibraryDraft,
    AssumptionLibraryManager,
    AssumptionLibraryVersion,
    build_seed_defaults,
)
from src.flywheel.calibration import CalibrationNote, CalibrationNoteStore
from src.flywheel.engagement_memory import EngagementMemory, EngagementMemoryStore
from src.flywheel.health import FlywheelHealth, FlywheelHealthService
from src.flywheel.mapping_library import (
    MappingLibraryDraft,
    MappingLibraryManager,
    MappingLibraryVersion,
)
from src.flywheel.models import PromotionStatus
from src.flywheel.publication import (
    FlywheelPublicationService,
    PublicationQualityGate,
    PublicationResult,
)
from src.flywheel.scenario_patterns import ScenarioPatternLibrary
from src.flywheel.stores import InMemoryVersionedLibraryStore
from src.flywheel.workforce_refinement import WorkforceBridgeRefinement
from src.models.common import AssumptionType, ConstraintConfidence, new_uuid7
from src.models.mapping import MappingLibraryEntry
from src.models.run import RunSnapshot


# ---------------------------------------------------------------------------
# Shared helper factories
# ---------------------------------------------------------------------------


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


def _make_override(
    line_item_text: str = "concrete supply",
    suggested_sector_code: str = "S01",
    final_sector_code: str = "S01",
    engagement_id: UUID | None = None,
) -> OverridePair:
    return OverridePair(
        engagement_id=engagement_id or new_uuid7(),
        line_item_id=new_uuid7(),
        line_item_text=line_item_text,
        suggested_sector_code=suggested_sector_code,
        final_sector_code=final_sector_code,
    )


def _make_classification(
    sector_code: str = "F",
    occupation_code: str = "7",
    tier: NationalityTier = NationalityTier.EXPAT_RELIANT,
    current_saudi_pct: float = 0.1,
) -> NationalityClassification:
    return NationalityClassification(
        sector_code=sector_code,
        occupation_code=occupation_code,
        tier=tier,
        current_saudi_pct=current_saudi_pct,
        rationale="Test classification",
        source_confidence=ConstraintConfidence.ESTIMATED,
        quality_confidence=QualityConfidence.MEDIUM,
        sensitivity_range=None,
        source="test",
    )


def _make_classification_set(
    classifications: list[NationalityClassification] | None = None,
) -> NationalityClassificationSet:
    if classifications is None:
        classifications = [
            _make_classification("F", "7"),
            _make_classification("C", "8", NationalityTier.SAUDI_TRAINABLE, 0.3),
            _make_classification("G", "5", NationalityTier.SAUDI_READY, 0.7),
        ]
    return NationalityClassificationSet(
        year=2024,
        classifications=classifications,
    )


def _make_workforce_override(
    sector_code: str = "F",
    occupation_code: str = "7",
    original_tier: NationalityTier = NationalityTier.EXPAT_RELIANT,
    override_tier: NationalityTier = NationalityTier.SAUDI_TRAINABLE,
) -> ClassificationOverride:
    return ClassificationOverride(
        sector_code=sector_code,
        occupation_code=occupation_code,
        original_tier=original_tier,
        override_tier=override_tier,
        overridden_by="analyst_1",
        engagement_id="eng-001",
        rationale="Updated based on field data",
        timestamp="2024-01-15T10:00:00Z",
    )


def _make_runsnapshot_kwargs() -> dict:
    """Return the minimum kwargs to construct a valid RunSnapshot."""
    return {
        "run_id": uuid4(),
        "model_version_id": uuid4(),
        "taxonomy_version_id": uuid4(),
        "concordance_version_id": uuid4(),
        "mapping_library_version_id": uuid4(),
        "assumption_library_version_id": uuid4(),
        "prompt_pack_version_id": uuid4(),
    }


def _wire_all_components() -> dict:
    """Create and wire all flywheel components together. Returns a dict of services."""
    mapping_manager = _make_mapping_manager()
    assumption_manager = _make_assumption_manager()
    pattern_library = ScenarioPatternLibrary()
    calibration_store = CalibrationNoteStore()
    memory_store = EngagementMemoryStore()
    workforce = WorkforceBridgeRefinement()

    publication_service = FlywheelPublicationService(
        mapping_manager=mapping_manager,
        assumption_manager=assumption_manager,
        pattern_library=pattern_library,
        workforce_refinement=workforce,
    )

    health_service = FlywheelHealthService(
        mapping_manager=mapping_manager,
        assumption_manager=assumption_manager,
        pattern_library=pattern_library,
        calibration_store=calibration_store,
        memory_store=memory_store,
        workforce_refinement=workforce,
    )

    return {
        "mapping_manager": mapping_manager,
        "assumption_manager": assumption_manager,
        "pattern_library": pattern_library,
        "calibration_store": calibration_store,
        "memory_store": memory_store,
        "workforce": workforce,
        "publication_service": publication_service,
        "health_service": health_service,
    }


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestFullMappingLifecycle:
    """Test 1: Create overrides -> build mapping draft -> publish ->
    RunSnapshot references the version -> get_version loads correct data.
    """

    def test_full_mapping_lifecycle(self) -> None:
        mapping_manager = _make_mapping_manager()
        publisher_id = new_uuid7()

        # Step 1: Create a LearningLoop and record overrides
        learning_loop = LearningLoop()
        eng_id = new_uuid7()
        for _ in range(3):
            learning_loop.record_override(
                _make_override(
                    line_item_text="steel rebar delivery",
                    suggested_sector_code="S01",
                    final_sector_code="S03",
                    engagement_id=eng_id,
                )
            )

        # Step 2: Build a mapping draft incorporating overrides
        draft = mapping_manager.build_draft(learning_loop=learning_loop)
        assert len(draft.entries) > 0
        assert len(draft.added_entry_ids) > 0

        # Step 3: Publish the draft
        version = mapping_manager.publish(draft, published_by=publisher_id)
        assert version.version_number == 1
        assert version.entry_count == len(draft.entries)

        # Step 4: Create a RunSnapshot referencing this version
        snap = RunSnapshot(
            **{
                **_make_runsnapshot_kwargs(),
                "mapping_library_version_id": version.version_id,
            }
        )
        assert snap.mapping_library_version_id == version.version_id

        # Step 5: Retrieve the version by ID from the RunSnapshot reference
        loaded_version = mapping_manager.get_version(
            snap.mapping_library_version_id
        )
        assert loaded_version is not None
        assert loaded_version.version_id == version.version_id
        assert loaded_version.version_number == 1
        assert loaded_version.entry_count == version.entry_count
        # Verify the actual entries are present and correct
        patterns = {e.pattern for e in loaded_version.entries}
        assert "steel rebar delivery" in patterns


class TestPublicationIdempotency:
    """Test 2: Publish cycle with no new changes creates no new versions."""

    def test_publish_idempotent_no_new_changes(self) -> None:
        mapping_manager = _make_mapping_manager()
        assumption_manager = _make_assumption_manager()
        workforce = WorkforceBridgeRefinement()
        pattern_library = ScenarioPatternLibrary()

        service = FlywheelPublicationService(
            mapping_manager=mapping_manager,
            assumption_manager=assumption_manager,
            pattern_library=pattern_library,
            workforce_refinement=workforce,
        )

        publisher_id = new_uuid7()

        # Initial publish: seed mapping and assumption data
        entries = [_make_entry("concrete supply", "S01")]
        m_draft = MappingLibraryDraft(entries=entries)
        mapping_manager.publish(m_draft, published_by=publisher_id)

        seed_defaults = build_seed_defaults()
        a_draft = AssumptionLibraryDraft(defaults=seed_defaults)
        assumption_manager.publish(a_draft, published_by=publisher_id)

        # Record version numbers before second cycle
        mapping_v1 = mapping_manager.get_active_version()
        assumption_v1 = assumption_manager.get_active_version()
        assert mapping_v1 is not None
        assert assumption_v1 is not None

        # Second publish cycle with NO new overrides
        result = service.publish_new_cycle(published_by=publisher_id)

        # No new versions should have been created (idempotent)
        assert result.mapping_version is None
        assert result.assumption_version is None

        # Active versions should still be v1
        mapping_active = mapping_manager.get_active_version()
        assumption_active = assumption_manager.get_active_version()
        assert mapping_active is not None
        assert mapping_active.version_id == mapping_v1.version_id
        assert assumption_active is not None
        assert assumption_active.version_id == assumption_v1.version_id


class TestAssumptionSectorLookup:
    """Test 3: Publish assumption library with seed defaults ->
    get_defaults_for_sector("F") returns Construction-specific + economy-wide defaults.
    """

    def test_sector_lookup_returns_sector_and_economy_wide(self) -> None:
        assumption_manager = _make_assumption_manager()
        publisher_id = new_uuid7()

        # Publish the seed defaults
        seed_defaults = build_seed_defaults()
        draft = AssumptionLibraryDraft(defaults=seed_defaults)
        version = assumption_manager.publish(draft, published_by=publisher_id)
        assert version.version_number == 1

        # Query for sector "F" (Construction)
        results = assumption_manager.get_defaults_for_sector("F")

        # Should include F-specific defaults AND economy-wide (sector_code=None)
        sector_codes = {d.sector_code for d in results}
        assert "F" in sector_codes
        assert None in sector_codes  # economy-wide defaults

        # Verify we get Construction import share (F-specific)
        f_import = [
            d
            for d in results
            if d.sector_code == "F"
            and d.assumption_type == AssumptionType.IMPORT_SHARE
        ]
        assert len(f_import) == 1
        assert f_import[0].default_numeric_value == 0.35

        # Verify we get economy-wide phasing default (None sector)
        phasing = [
            d
            for d in results
            if d.sector_code is None
            and d.assumption_type == AssumptionType.PHASING
        ]
        assert len(phasing) == 1
        assert phasing[0].default_text_value == "even"

        # Verify we get F-specific JOBS_COEFF
        jobs = [
            d
            for d in results
            if d.sector_code == "F"
            and d.assumption_type == AssumptionType.JOBS_COEFF
        ]
        assert len(jobs) == 1
        assert jobs[0].default_numeric_value == 18.5

        # Should NOT include C-specific or K-specific defaults
        assert "C" not in sector_codes
        assert "K" not in sector_codes


class TestScenarioPatternAccumulation:
    """Test 4: Record 3 similar engagements -> suggest_template returns
    merged pattern with correct engagement_count.
    """

    def test_similar_engagements_merge_into_single_pattern(self) -> None:
        pattern_library = ScenarioPatternLibrary()

        # Record 3 similar logistics zone engagements with nearly identical shares
        eng_ids = [new_uuid7() for _ in range(3)]
        spec_ids = [new_uuid7() for _ in range(3)]

        shares_list = [
            {"F": 0.60, "C": 0.25, "H": 0.15},
            {"F": 0.58, "C": 0.27, "H": 0.15},
            {"F": 0.62, "C": 0.24, "H": 0.14},
        ]

        for eng_id, spec_id, shares in zip(eng_ids, spec_ids, shares_list):
            pattern_library.record_engagement_pattern(
                engagement_id=eng_id,
                scenario_spec_id=spec_id,
                project_type="logistics_zone",
                sector_shares=shares,
                import_share=0.35,
                duration_years=5,
            )

        # After 3 similar engagements, they should merge into 1 pattern
        all_patterns = pattern_library.find_patterns(
            project_type="logistics_zone"
        )
        assert len(all_patterns) == 1

        # suggest_template returns the merged pattern
        template = pattern_library.suggest_template("logistics_zone")
        assert template is not None
        assert template.engagement_count == 3

        # All 3 engagement IDs should be in contributing_engagement_ids
        assert len(template.contributing_engagement_ids) == 3
        for eng_id in eng_ids:
            assert eng_id in template.contributing_engagement_ids

        # Sector shares should be rolling averages
        assert "F" in template.typical_sector_shares
        assert "C" in template.typical_sector_shares
        assert "H" in template.typical_sector_shares

        # Confidence should be "medium" at 3 engagements
        assert template.confidence == "medium"


class TestCalibrationNotePromotionPath:
    """Test 5: Create calibration note -> mark promoted -> verify
    promotion_status changes.
    """

    def test_calibration_note_promotion_lifecycle(self) -> None:
        calibration_store = CalibrationNoteStore()
        workspace_id = new_uuid7()
        user_id = new_uuid7()
        engagement_id = new_uuid7()

        # Step 1: Create calibration note (starts as RAW)
        note = CalibrationNote(
            sector_code="F",
            engagement_id=engagement_id,
            observation="Construction multiplier overstated employment by ~15%",
            likely_cause="Outdated GOSI data used for employment coefficients",
            recommended_adjustment="Reduce jobs_coeff for F from 18.5 to 15.7",
            metric_affected="employment",
            direction="overstate",
            magnitude_estimate=0.15,
            created_by=user_id,
            workspace_id=workspace_id,
        )
        calibration_store.append(note)

        # Verify initial state
        loaded = calibration_store.get(note.note_id)
        assert loaded is not None
        assert loaded.promotion_status == PromotionStatus.RAW
        assert loaded.promoted_to is None

        # Step 2: Mark as REVIEWED
        loaded.promotion_status = PromotionStatus.REVIEWED
        reviewed = calibration_store.get(note.note_id)
        assert reviewed is not None
        assert reviewed.promotion_status == PromotionStatus.REVIEWED

        # Step 3: Promote to an assumption default
        target_assumption_id = new_uuid7()
        loaded.promotion_status = PromotionStatus.PROMOTED
        loaded.promoted_to = target_assumption_id

        promoted = calibration_store.get(note.note_id)
        assert promoted is not None
        assert promoted.promotion_status == PromotionStatus.PROMOTED
        assert promoted.promoted_to == target_assumption_id

        # Step 4: Verify it can be found by sector and metric
        by_sector = calibration_store.find_by_sector("F")
        assert len(by_sector) == 1
        assert by_sector[0].note_id == note.note_id

        by_metric = calibration_store.find_by_metric("employment")
        assert len(by_metric) == 1
        assert by_metric[0].promotion_status == PromotionStatus.PROMOTED


class TestEngagementMemoryPromotionPath:
    """Test 6: Create engagement memory -> mark promoted -> verify."""

    def test_engagement_memory_promotion_lifecycle(self) -> None:
        memory_store = EngagementMemoryStore()
        workspace_id = new_uuid7()
        user_id = new_uuid7()
        engagement_id = new_uuid7()

        # Step 1: Create engagement memory (starts as RAW)
        memory = EngagementMemory(
            engagement_id=engagement_id,
            category="challenge",
            description="Client challenged the import share for steel fabrication",
            sector_code="C",
            resolution="Provided customs data from 2023 validating 0.45 ratio",
            time_to_resolve="3 days",
            lesson_learned="Always pre-load customs evidence for manufacturing",
            created_by=user_id,
            tags=["import_share", "manufacturing", "evidence"],
            workspace_id=workspace_id,
        )
        memory_store.append(memory)

        # Verify initial state
        loaded = memory_store.get(memory.memory_id)
        assert loaded is not None
        assert loaded.promotion_status == PromotionStatus.RAW
        assert loaded.promoted_to is None

        # Step 2: Mark as REVIEWED
        loaded.promotion_status = PromotionStatus.REVIEWED
        reviewed = memory_store.get(memory.memory_id)
        assert reviewed is not None
        assert reviewed.promotion_status == PromotionStatus.REVIEWED

        # Step 3: Promote to a governance rule
        target_rule_id = new_uuid7()
        loaded.promotion_status = PromotionStatus.PROMOTED
        loaded.promoted_to = target_rule_id

        promoted = memory_store.get(memory.memory_id)
        assert promoted is not None
        assert promoted.promotion_status == PromotionStatus.PROMOTED
        assert promoted.promoted_to == target_rule_id

        # Step 4: Verify searchability
        by_category = memory_store.find_by_category("challenge")
        assert len(by_category) == 1
        assert by_category[0].memory_id == memory.memory_id

        by_tags = memory_store.find_by_tags(["import_share"])
        assert len(by_tags) == 1

        by_sector = memory_store.find_by_sector("C")
        assert len(by_sector) == 1


class TestWorkforceRefinementLifecycle:
    """Test 7: Record overrides -> build refined classifications -> verify
    tier changed.
    """

    def test_workforce_refinement_end_to_end(self) -> None:
        workforce = WorkforceBridgeRefinement()
        eng_id_1 = new_uuid7()
        eng_id_2 = new_uuid7()

        # Step 1: Record overrides from first engagement
        overrides_1 = [
            _make_workforce_override(
                "F",
                "7",
                NationalityTier.EXPAT_RELIANT,
                NationalityTier.SAUDI_TRAINABLE,
            ),
        ]
        workforce.record_engagement_overrides(eng_id_1, overrides_1)

        # Step 2: Record overrides from second engagement
        overrides_2 = [
            _make_workforce_override(
                "C",
                "8",
                NationalityTier.SAUDI_TRAINABLE,
                NationalityTier.SAUDI_READY,
            ),
        ]
        workforce.record_engagement_overrides(eng_id_2, overrides_2)

        # Step 3: Verify coverage
        coverage = workforce.get_refinement_coverage()
        assert coverage["engagement_count"] == 2
        assert coverage["engagement_calibrated_cells"] == 2

        # Step 4: Build refined classifications from a base set
        base = _make_classification_set()
        refined = workforce.build_refined_classifications(base)

        # Step 5: Verify tier changed for F/7
        entry_f7 = refined.get_tier("F", "7")
        assert entry_f7 is not None
        assert entry_f7.tier == NationalityTier.SAUDI_TRAINABLE  # was EXPAT_RELIANT

        # Step 6: Verify tier changed for C/8
        entry_c8 = refined.get_tier("C", "8")
        assert entry_c8 is not None
        assert entry_c8.tier == NationalityTier.SAUDI_READY  # was SAUDI_TRAINABLE

        # Step 7: Unchanged entry remains the same
        entry_g5 = refined.get_tier("G", "5")
        assert entry_g5 is not None
        assert entry_g5.tier == NationalityTier.SAUDI_READY  # unchanged


class TestFullPublicationCycle:
    """Test 8: Wire all components -> publish_new_cycle -> verify all
    versions created and health metrics updated.
    """

    def test_full_publication_cycle_with_health(self) -> None:
        components = _wire_all_components()
        mapping_manager: MappingLibraryManager = components["mapping_manager"]
        assumption_manager: AssumptionLibraryManager = components["assumption_manager"]
        pattern_library: ScenarioPatternLibrary = components["pattern_library"]
        calibration_store: CalibrationNoteStore = components["calibration_store"]
        memory_store: EngagementMemoryStore = components["memory_store"]
        workforce: WorkforceBridgeRefinement = components["workforce"]
        publication_service: FlywheelPublicationService = components[
            "publication_service"
        ]
        health_service: FlywheelHealthService = components["health_service"]

        publisher_id = new_uuid7()

        # ----- Step 1: Check initial health (everything zero) -----
        health_before = health_service.compute_health()
        assert health_before.mapping_library_version == 0
        assert health_before.assumption_library_version == 0
        assert health_before.scenario_pattern_count == 0
        assert health_before.calibration_note_count == 0
        assert health_before.engagement_memory_count == 0

        # ----- Step 2: Populate calibration notes -----
        note = CalibrationNote(
            sector_code="F",
            observation="Employment coefficient seems high",
            likely_cause="Outdated data",
            metric_affected="employment",
            direction="overstate",
            created_by=publisher_id,
            workspace_id=new_uuid7(),
        )
        calibration_store.append(note)

        # ----- Step 3: Populate engagement memories -----
        memory = EngagementMemory(
            engagement_id=new_uuid7(),
            category="challenge",
            description="Client challenged import share",
            created_by=publisher_id,
            workspace_id=new_uuid7(),
        )
        memory_store.append(memory)

        # ----- Step 4: Record scenario patterns -----
        pattern_library.record_engagement_pattern(
            engagement_id=new_uuid7(),
            scenario_spec_id=new_uuid7(),
            project_type="giga_project",
            sector_shares={"F": 0.5, "C": 0.3, "H": 0.2},
        )

        # ----- Step 5: Record workforce overrides -----
        workforce.record_engagement_overrides(
            new_uuid7(),
            [
                _make_workforce_override(
                    "F",
                    "7",
                    NationalityTier.EXPAT_RELIANT,
                    NationalityTier.SAUDI_TRAINABLE,
                )
            ],
        )

        # ----- Step 6: Create learning loop with overrides -----
        learning_loop = LearningLoop()
        for _ in range(3):
            learning_loop.record_override(
                _make_override(
                    line_item_text="heavy machinery rental",
                    suggested_sector_code="S01",
                    final_sector_code="S05",
                )
            )

        # ----- Step 7: Run full publication cycle -----
        result = publication_service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=learning_loop,
            steward_approved=True,
        )

        assert isinstance(result, PublicationResult)
        # Mapping should have been published (learning loop created new patterns)
        assert result.mapping_version is not None
        assert result.mapping_version.version_number == 1
        assert result.new_patterns > 0

        # Workforce coverage should be populated
        assert result.workforce_coverage["engagement_count"] == 1

        # Summary should be non-empty
        assert result.summary != ""

        # ----- Step 8: Check health metrics after publication -----
        health_after = health_service.compute_health()
        assert health_after.mapping_library_version == 1
        assert health_after.mapping_entry_count > 0
        assert health_after.scenario_pattern_count == 1
        assert health_after.calibration_note_count == 1
        assert health_after.engagement_memory_count == 1
        assert health_after.last_publication is not None

        # ----- Step 9: Verify RunSnapshot can reference published versions -----
        active_mapping = mapping_manager.get_active_version()
        assert active_mapping is not None
        snap = RunSnapshot(
            **{
                **_make_runsnapshot_kwargs(),
                "mapping_library_version_id": active_mapping.version_id,
            }
        )
        loaded = mapping_manager.get_version(snap.mapping_library_version_id)
        assert loaded is not None
        assert loaded.version_id == active_mapping.version_id


class TestMappingVersionMonotonicity:
    """Test 9: Verify version numbers increase monotonically across
    multiple publication cycles.
    """

    def test_version_numbers_increase_monotonically(self) -> None:
        mapping_manager = _make_mapping_manager()
        publisher_id = new_uuid7()

        version_numbers: list[int] = []

        # Publish 5 versions with different entries each time
        for i in range(5):
            draft = MappingLibraryDraft(
                entries=[_make_entry(f"pattern_{i}", f"S{i:02d}")]
            )
            version = mapping_manager.publish(draft, published_by=publisher_id)
            version_numbers.append(version.version_number)

        # All version numbers should be strictly increasing
        for j in range(1, len(version_numbers)):
            assert version_numbers[j] > version_numbers[j - 1]

        # They should be 1, 2, 3, 4, 5
        assert version_numbers == [1, 2, 3, 4, 5]

        # get_active_version should return the latest
        active = mapping_manager.get_active_version()
        assert active is not None
        assert active.version_number == 5

        # All versions should be retrievable
        all_versions = mapping_manager.list_versions()
        assert len(all_versions) == 5


class TestCrossComponentDataFlow:
    """Test 10: Verify data flows correctly across multiple components
    in a realistic multi-engagement scenario.
    """

    def test_multi_engagement_flywheel_accumulation(self) -> None:
        components = _wire_all_components()
        mapping_manager: MappingLibraryManager = components["mapping_manager"]
        assumption_manager: AssumptionLibraryManager = components["assumption_manager"]
        pattern_library: ScenarioPatternLibrary = components["pattern_library"]
        calibration_store: CalibrationNoteStore = components["calibration_store"]
        memory_store: EngagementMemoryStore = components["memory_store"]
        health_service: FlywheelHealthService = components["health_service"]

        publisher_id = new_uuid7()
        workspace_id = new_uuid7()

        # ----- Engagement 1: seed the system -----
        eng_1_id = new_uuid7()
        pattern_library.record_engagement_pattern(
            engagement_id=eng_1_id,
            scenario_spec_id=new_uuid7(),
            project_type="housing",
            sector_shares={"F": 0.70, "C": 0.20, "G": 0.10},
        )
        calibration_store.append(
            CalibrationNote(
                sector_code="F",
                engagement_id=eng_1_id,
                observation="Employment multiplier reasonable",
                likely_cause="Good data quality",
                metric_affected="employment",
                direction="overstate",
                magnitude_estimate=0.03,
                created_by=publisher_id,
                workspace_id=workspace_id,
            )
        )

        # ----- Engagement 2: accumulate more data -----
        eng_2_id = new_uuid7()
        pattern_library.record_engagement_pattern(
            engagement_id=eng_2_id,
            scenario_spec_id=new_uuid7(),
            project_type="housing",
            sector_shares={"F": 0.68, "C": 0.22, "G": 0.10},
        )
        memory_store.append(
            EngagementMemory(
                engagement_id=eng_2_id,
                category="evidence_request",
                description="Ministry requested additional data on local content",
                created_by=publisher_id,
                tags=["local_content"],
                workspace_id=workspace_id,
            )
        )

        # ----- Engagement 3: even more -----
        eng_3_id = new_uuid7()
        pattern_library.record_engagement_pattern(
            engagement_id=eng_3_id,
            scenario_spec_id=new_uuid7(),
            project_type="housing",
            sector_shares={"F": 0.72, "C": 0.18, "G": 0.10},
        )

        # ----- Verify accumulated state -----

        # Patterns should have merged into 1 for housing
        housing_patterns = pattern_library.find_patterns(
            project_type="housing"
        )
        assert len(housing_patterns) == 1
        assert housing_patterns[0].engagement_count == 3

        # Template suggestion should work
        template = pattern_library.suggest_template("housing")
        assert template is not None
        assert template.confidence == "medium"  # 3 engagements

        # Health metrics reflect all components
        health = health_service.compute_health()
        assert health.scenario_pattern_count == 1
        assert health.calibration_note_count == 1
        assert health.engagement_memory_count == 1

        # Publish assumption library so health reflects it
        seed_defaults = build_seed_defaults()
        a_draft = AssumptionLibraryDraft(defaults=seed_defaults)
        assumption_manager.publish(a_draft, published_by=publisher_id)

        health_after = health_service.compute_health()
        assert health_after.assumption_library_version == 1
        assert health_after.assumption_default_count == 7  # seed has 7 defaults
