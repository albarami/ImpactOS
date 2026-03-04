"""Integration Path 5: Flywheel Learning Loop (module-level).

Tests the direct Python API (not HTTP):
- LearningLoop.record_override -> extract_new_patterns -> MappingLibraryManager
- FlywheelPublicationService.publish_new_cycle
- Quality gate rejects low-frequency patterns
- Scope isolation

Uses SEED_LIBRARY from shared.py for realistic initial library state.
"""

import pytest
from uuid_extensions import uuid7

from src.compiler.learning import LearningLoop, OverridePair
from src.flywheel.assumption_library import AssumptionLibraryManager
from src.flywheel.mapping_library import MappingLibraryManager, MappingLibraryVersion
from src.flywheel.publication import (
    FlywheelPublicationService,
    PublicationQualityGate,
    PublicationResult,
)
from src.flywheel.scenario_patterns import ScenarioPatternLibrary
from src.flywheel.stores import InMemoryVersionedLibraryStore
from src.flywheel.workforce_refinement import WorkforceBridgeRefinement
from src.models.mapping import MappingLibraryEntry
from tests.integration.golden_scenarios.shared import SEED_LIBRARY

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def learning_loop() -> LearningLoop:
    return LearningLoop()


@pytest.fixture
def mapping_manager() -> MappingLibraryManager:
    store: InMemoryVersionedLibraryStore[MappingLibraryVersion] = (
        InMemoryVersionedLibraryStore()
    )
    return MappingLibraryManager(store)


@pytest.fixture
def publication_service() -> FlywheelPublicationService:
    mm = MappingLibraryManager(InMemoryVersionedLibraryStore())
    am = AssumptionLibraryManager(InMemoryVersionedLibraryStore())
    sp = ScenarioPatternLibrary()
    wr = WorkforceBridgeRefinement()
    return FlywheelPublicationService(mm, am, sp, wr)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.gate
class TestFlywheelLearningIntegration:
    """Override -> pattern extraction -> draft build -> publish cycle."""

    def test_record_override_creates_pair(self, learning_loop: LearningLoop) -> None:
        """record_override stores an OverridePair retrievable via get_overrides."""
        engagement_id = uuid7()
        pair = OverridePair(
            engagement_id=engagement_id,
            line_item_id=uuid7(),
            line_item_text="concrete foundation works",
            suggested_sector_code="C",
            final_sector_code="F",
            project_type="industrial",
        )
        learning_loop.record_override(pair)

        overrides = learning_loop.get_overrides()
        assert len(overrides) == 1
        assert overrides[0].override_id == pair.override_id
        assert overrides[0].engagement_id == engagement_id
        assert overrides[0].line_item_text == "concrete foundation works"
        assert overrides[0].suggested_sector_code == "C"
        assert overrides[0].final_sector_code == "F"
        assert overrides[0].was_correct is False  # C != F

    def test_extract_patterns_from_overrides(
        self, learning_loop: LearningLoop
    ) -> None:
        """Repeated overrides (>= min_frequency) produce new MappingLibraryEntry patterns."""
        engagement_id = uuid7()

        # Record the same override pattern 3 times (above min_frequency=2)
        for _ in range(3):
            learning_loop.record_override(
                OverridePair(
                    engagement_id=engagement_id,
                    line_item_id=uuid7(),
                    line_item_text="concrete foundation works",
                    suggested_sector_code="C",
                    final_sector_code="F",
                    project_type="industrial",
                )
            )

        overrides = learning_loop.get_overrides()
        patterns = learning_loop.extract_new_patterns(
            overrides=overrides,
            existing_library=[],
            min_frequency=2,
        )

        assert len(patterns) >= 1
        # The extracted pattern should target sector F (the final_sector_code)
        f_patterns = [p for p in patterns if p.sector_code == "F"]
        assert len(f_patterns) >= 1
        assert f_patterns[0].pattern == "concrete foundation works"
        # Confidence: 0 correct out of 3 (suggested C, final F -> not correct)
        assert f_patterns[0].confidence == 0.0

    def test_extract_patterns_respects_min_frequency(
        self, learning_loop: LearningLoop
    ) -> None:
        """Single occurrence does not produce a pattern when min_frequency=2."""
        learning_loop.record_override(
            OverridePair(
                engagement_id=uuid7(),
                line_item_id=uuid7(),
                line_item_text="very unique procurement item",
                suggested_sector_code="G",
                final_sector_code="F",
                project_type="custom",
            )
        )

        overrides = learning_loop.get_overrides()
        patterns = learning_loop.extract_new_patterns(
            overrides=overrides,
            existing_library=[],
            min_frequency=2,
        )
        assert len(patterns) == 0

    def test_extract_patterns_deduplicates_against_existing(
        self, learning_loop: LearningLoop
    ) -> None:
        """Patterns already in SEED_LIBRARY are not re-extracted."""
        engagement_id = uuid7()

        # Record overrides matching an existing SEED_LIBRARY entry
        # SEED_LIBRARY has: pattern="concrete", sector_code="F"
        for _ in range(3):
            learning_loop.record_override(
                OverridePair(
                    engagement_id=engagement_id,
                    line_item_id=uuid7(),
                    line_item_text="concrete",
                    suggested_sector_code="C",
                    final_sector_code="F",
                    project_type="industrial",
                )
            )

        overrides = learning_loop.get_overrides()
        patterns = learning_loop.extract_new_patterns(
            overrides=overrides,
            existing_library=SEED_LIBRARY,
            min_frequency=2,
        )

        # "concrete" + "F" already exists in SEED_LIBRARY, should be skipped
        assert all(
            not (p.pattern == "concrete" and p.sector_code == "F")
            for p in patterns
        )

    def test_build_draft_library_from_patterns(
        self,
        learning_loop: LearningLoop,
        mapping_manager: MappingLibraryManager,
    ) -> None:
        """MappingLibraryManager.build_draft incorporates learning loop overrides."""
        engagement_id = uuid7()

        # Record overrides for a novel pattern
        for _ in range(3):
            learning_loop.record_override(
                OverridePair(
                    engagement_id=engagement_id,
                    line_item_id=uuid7(),
                    line_item_text="specialized piping installation",
                    suggested_sector_code="C",
                    final_sector_code="F",
                    project_type="industrial",
                )
            )

        # Build a draft with the learning loop (no base version)
        draft = mapping_manager.build_draft(
            base_version_id=None,
            learning_loop=learning_loop,
        )

        # Draft should contain the new pattern from overrides
        assert len(draft.entries) >= 1
        assert len(draft.added_entry_ids) >= 1
        found = [
            e
            for e in draft.entries
            if e.pattern == "specialized piping installation" and e.sector_code == "F"
        ]
        assert len(found) == 1
        assert any(
            "specialized piping installation" in c for c in draft.changes_from_parent
        )

    def test_build_draft_updates_confidence_on_existing(
        self,
        learning_loop: LearningLoop,
        mapping_manager: MappingLibraryManager,
    ) -> None:
        """build_draft updates confidence on existing entries using override accuracy."""
        publisher_id = uuid7()

        # Publish a v1 with a seed entry
        seed_entry = MappingLibraryEntry(
            pattern="steel beams", sector_code="C", confidence=0.90
        )
        from src.flywheel.mapping_library import MappingLibraryDraft
        from src.flywheel.models import DraftStatus

        seed_draft = MappingLibraryDraft(
            entries=[seed_entry],
            status=DraftStatus.DRAFT,
        )
        v1 = mapping_manager.publish(seed_draft, published_by=publisher_id)

        # Record overrides where suggested=C and all are correct (suggested == final)
        for _ in range(3):
            learning_loop.record_override(
                OverridePair(
                    engagement_id=uuid7(),
                    line_item_id=uuid7(),
                    line_item_text="steel beams for structure",
                    suggested_sector_code="C",
                    final_sector_code="C",
                    project_type="industrial",
                )
            )

        # Build draft from v1 with learning loop
        draft = mapping_manager.build_draft(
            base_version_id=v1.version_id,
            learning_loop=learning_loop,
        )

        # Confidence should be updated: (0.90 + 1.0) / 2 = 0.95
        steel_entries = [e for e in draft.entries if e.pattern == "steel beams"]
        assert len(steel_entries) == 1
        assert abs(steel_entries[0].confidence - 0.95) < 1e-6

    def test_override_to_publish_cycle(self) -> None:
        """Full flywheel round trip: override -> extract -> draft -> publish."""
        # Set up fresh managers
        mm = MappingLibraryManager(InMemoryVersionedLibraryStore())
        am = AssumptionLibraryManager(InMemoryVersionedLibraryStore())
        sp = ScenarioPatternLibrary()
        wr = WorkforceBridgeRefinement()
        pub_service = FlywheelPublicationService(mm, am, sp, wr)
        loop = LearningLoop()

        engagement_id = uuid7()
        publisher_id = uuid7()

        # Step 1: Record overrides (analyst corrects AI suggestions)
        for _ in range(4):
            loop.record_override(
                OverridePair(
                    engagement_id=engagement_id,
                    line_item_id=uuid7(),
                    line_item_text="heavy equipment rental services",
                    suggested_sector_code="C",
                    final_sector_code="N",
                    project_type="logistics",
                )
            )

        assert loop.total_overrides() == 4

        # Step 2: Publish cycle with learning loop
        result = pub_service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=loop,
            steward_approved=True,
        )

        # Step 3: Verify publication result
        assert isinstance(result, PublicationResult)
        assert result.new_patterns >= 1
        assert result.mapping_version is not None
        assert result.mapping_version.version_number == 1
        assert result.mapping_version.entry_count >= 1

        # The published version should contain our new pattern
        published_entries = result.mapping_version.entries
        rental_entries = [
            e
            for e in published_entries
            if e.pattern == "heavy equipment rental services"
            and e.sector_code == "N"
        ]
        assert len(rental_entries) == 1

        # Workforce coverage dict should be present
        assert isinstance(result.workforce_coverage, dict)

        # Summary should mention the publication
        assert "Published mapping library" in result.summary

    def test_quality_gate_blocks_without_steward(self) -> None:
        """Quality gate rejects publication when steward_approved=False."""
        mm = MappingLibraryManager(InMemoryVersionedLibraryStore())
        am = AssumptionLibraryManager(InMemoryVersionedLibraryStore())
        sp = ScenarioPatternLibrary()
        wr = WorkforceBridgeRefinement()
        pub_service = FlywheelPublicationService(mm, am, sp, wr)
        loop = LearningLoop()

        # Record overrides to have content to publish
        for _ in range(3):
            loop.record_override(
                OverridePair(
                    engagement_id=uuid7(),
                    line_item_id=uuid7(),
                    line_item_text="gate test item",
                    suggested_sector_code="A",
                    final_sector_code="B",
                    project_type="mining",
                )
            )

        gate = PublicationQualityGate(require_steward_review=True)

        result = pub_service.publish_new_cycle(
            published_by=uuid7(),
            learning_loop=loop,
            steward_approved=False,
            quality_gate=gate,
        )

        # Mapping should NOT be published (gate failed)
        assert result.mapping_version is None
        # But new_patterns still counted (they were extracted, just not published)
        assert result.new_patterns >= 1

    def test_flywheel_health_metrics(self) -> None:
        """get_flywheel_health returns meaningful metrics dict."""
        mm = MappingLibraryManager(InMemoryVersionedLibraryStore())
        am = AssumptionLibraryManager(InMemoryVersionedLibraryStore())
        sp = ScenarioPatternLibrary()
        wr = WorkforceBridgeRefinement()
        pub_service = FlywheelPublicationService(mm, am, sp, wr)

        health = pub_service.get_flywheel_health()

        assert isinstance(health, dict)
        assert "mapping_version" in health
        assert "assumption_version" in health
        assert "pattern_count" in health
        assert "workforce_coverage" in health
        # No versions published yet
        assert health["mapping_version"] is None
        assert health["assumption_version"] is None
        assert health["pattern_count"] == 0

    def test_idempotent_publish_no_changes(self) -> None:
        """Publishing twice with no new overrides does not create duplicate versions."""
        mm = MappingLibraryManager(InMemoryVersionedLibraryStore())
        am = AssumptionLibraryManager(InMemoryVersionedLibraryStore())
        sp = ScenarioPatternLibrary()
        wr = WorkforceBridgeRefinement()
        pub_service = FlywheelPublicationService(mm, am, sp, wr)
        loop = LearningLoop()
        publisher_id = uuid7()

        # Record overrides and publish first cycle
        for _ in range(3):
            loop.record_override(
                OverridePair(
                    engagement_id=uuid7(),
                    line_item_id=uuid7(),
                    line_item_text="idempotent test pattern",
                    suggested_sector_code="G",
                    final_sector_code="H",
                    project_type="transport",
                )
            )

        result1 = pub_service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=loop,
            steward_approved=True,
        )
        assert result1.mapping_version is not None
        assert result1.mapping_version.version_number == 1

        # Second publish with same loop (no new overrides) -> no new version
        result2 = pub_service.publish_new_cycle(
            published_by=publisher_id,
            learning_loop=loop,
            steward_approved=True,
        )
        # Same content -> mapping_version should be None (no change)
        assert result2.mapping_version is None
        assert "No changes" in result2.summary
