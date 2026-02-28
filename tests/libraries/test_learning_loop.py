"""Tests for LibraryLearningLoop (MVP-12).

Event-driven learning: HITL actions trigger library updates.
"""

from uuid_extensions import uuid7

from src.models.common import ConstraintConfidence
from src.models.libraries import (
    AssumptionLibraryEntry,
    EntryStatus,
    LibraryAssumptionType,
    MappingLibraryEntry,
)


class TestLibraryLearningLoop:
    def _make_loop(self):
        from src.libraries.assumption_library import AssumptionLibraryService
        from src.libraries.learning_loop import LibraryLearningLoop
        from src.libraries.mapping_library import MappingLibraryService
        from src.libraries.scenario_patterns import ScenarioPatternService

        mapping_svc = MappingLibraryService([])
        assumption_svc = AssumptionLibraryService([])
        pattern_svc = ScenarioPatternService([])
        return LibraryLearningLoop(
            mapping_service=mapping_svc,
            assumption_service=assumption_svc,
            pattern_service=pattern_svc,
        )

    def test_on_mapping_approved_new_entry(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        result = loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        assert isinstance(result, MappingLibraryEntry)
        assert result.sector_code == "F"
        assert result.status == EntryStatus.DRAFT

    def test_on_mapping_approved_existing_increments(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        r1 = loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        r2 = loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        # Second call should increment usage on existing
        assert len(loop._mapping_service._entries) == 1
        assert loop._mapping_service._entries[0].usage_count >= 1

    def test_on_mapping_overridden_creates_correction(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        result = loop.on_mapping_overridden(
            line_item_text="steel fabrication works",
            original_sector="C",
            final_sector="F",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        assert isinstance(result, MappingLibraryEntry)
        assert result.sector_code == "F"  # Uses final_sector
        assert result.confidence == 0.9  # High confidence for overrides

    def test_on_mapping_overridden_tracks_engagement(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        eng_id = uuid7()
        result = loop.on_mapping_overridden(
            line_item_text="steel fabrication works",
            original_sector="C",
            final_sector="F",
            engagement_id=eng_id,
            workspace_id=ws,
        )
        assert result.source_engagement_id == eng_id

    def test_on_assumption_approved_new_entry(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        result = loop.on_assumption_approved(
            assumption_type=LibraryAssumptionType.IMPORT_SHARE,
            sector_code="F",
            value=0.35,
            range_low=0.20,
            range_high=0.50,
            unit="fraction",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        assert isinstance(result, AssumptionLibraryEntry)
        assert result.default_value == 0.35
        assert result.status == EntryStatus.DRAFT

    def test_on_engagement_completed_creates_pattern(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        result = loop.on_engagement_completed(
            engagement_id=uuid7(),
            workspace_id=ws,
            sector_codes=["F", "C"],
            shock_types=["FINAL_DEMAND"],
        )
        # Should create pattern when >= 2 sectors + >= 1 shock
        assert result is not None
        assert set(result.sector_focus) == {"F", "C"}

    def test_on_engagement_completed_insufficient_data(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        result = loop.on_engagement_completed(
            engagement_id=uuid7(),
            workspace_id=ws,
            sector_codes=["F"],  # Only 1 sector
            shock_types=[],  # No shocks
        )
        assert result is None

    def test_growth_metrics_empty(self) -> None:
        loop = self._make_loop()
        metrics = loop.get_growth_metrics()
        assert metrics["mapping_entries"] == 0
        assert metrics["assumption_entries"] == 0
        assert metrics["scenario_patterns"] == 0

    def test_growth_metrics_after_approvals(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        loop.on_assumption_approved(
            assumption_type=LibraryAssumptionType.IMPORT_SHARE,
            sector_code="F",
            value=0.35,
            range_low=0.20,
            range_high=0.50,
            unit="fraction",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        metrics = loop.get_growth_metrics()
        assert metrics["mapping_entries"] == 1
        assert metrics["assumption_entries"] == 1

    def test_growth_metrics_after_overrides(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        loop.on_mapping_overridden(
            line_item_text="steel fabrication",
            original_sector="C",
            final_sector="F",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        metrics = loop.get_growth_metrics()
        assert metrics["mapping_entries"] == 1
        assert metrics["overrides_captured"] == 1

    def test_workspace_isolation(self) -> None:
        loop = self._make_loop()
        ws1, ws2 = uuid7(), uuid7()
        loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=uuid7(),
            workspace_id=ws1,
        )
        loop.on_mapping_approved(
            line_item_text="electrical wiring cables",
            sector_code="D",
            engagement_id=uuid7(),
            workspace_id=ws2,
        )
        assert len(loop._mapping_service._entries) == 2

    def test_actor_tracking(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        actor = uuid7()
        result = loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=uuid7(),
            workspace_id=ws,
            actor=actor,
        )
        assert result.created_by == actor

    def test_override_confidence_is_high(self) -> None:
        loop = self._make_loop()
        ws = uuid7()
        result = loop.on_mapping_overridden(
            line_item_text="steel fabrication works",
            original_sector="C",
            final_sector="F",
            engagement_id=uuid7(),
            workspace_id=ws,
        )
        # Overrides are high-value learning → high confidence
        assert result.confidence >= 0.9

    def test_idempotency_key_tracking(self) -> None:
        """Amendment 3: Duplicate events should not create duplicate entries."""
        loop = self._make_loop()
        ws = uuid7()
        eng = uuid7()
        r1 = loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=eng,
            workspace_id=ws,
        )
        # Same event again
        r2 = loop.on_mapping_approved(
            line_item_text="concrete reinforcement steel",
            sector_code="F",
            engagement_id=eng,
            workspace_id=ws,
        )
        # Should have been handled as reinforcement, not duplicate entry
        assert len(loop._mapping_service._entries) == 1
