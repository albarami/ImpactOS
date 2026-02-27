"""Library-aware Learning Loop — MVP-12.

Event-driven: HITL analyst actions trigger library updates.
Wraps MappingLibraryService, AssumptionLibraryService, ScenarioPatternService.

Amendment 3: Called from compiler.py bulk_decisions.
Amendment 7: Auto-captured entries start as DRAFT.
"""

from uuid import UUID

from src.models.common import ConstraintConfidence, utc_now
from src.models.libraries import (
    AssumptionLibraryEntry,
    EntryStatus,
    LibraryAssumptionType,
    MappingLibraryEntry,
    ScenarioPattern,
)

from src.libraries.assumption_library import AssumptionLibraryService
from src.libraries.mapping_library import MappingLibraryService
from src.libraries.scenario_patterns import ScenarioPatternService


class LibraryLearningLoop:
    """Connects analyst actions to library growth.

    Every approved mapping, override, or assumption creates or reinforces
    library entries. This is the flywheel mechanism.
    """

    def __init__(
        self,
        mapping_service: MappingLibraryService,
        assumption_service: AssumptionLibraryService,
        pattern_service: ScenarioPatternService,
    ) -> None:
        self._mapping_service = mapping_service
        self._assumption_service = assumption_service
        self._pattern_service = pattern_service
        self._overrides_captured: int = 0

    def on_mapping_approved(
        self,
        *,
        line_item_text: str,
        sector_code: str,
        engagement_id: UUID,
        workspace_id: UUID,
        confidence: float = 0.8,
        actor: UUID | None = None,
    ) -> MappingLibraryEntry:
        """Add to library or increment usage when analyst approves a mapping.

        Auto-captured entries start as DRAFT (Amendment 7).
        Duplicate pattern+sector → reinforcement (Amendment 3 idempotency).
        """
        entry = MappingLibraryEntry(
            workspace_id=workspace_id,
            pattern=line_item_text,
            sector_code=sector_code,
            confidence=confidence,
            source_engagement_id=engagement_id,
            created_by=actor,
            status=EntryStatus.DRAFT,
        )
        return self._mapping_service.add_entry(entry)

    def on_mapping_overridden(
        self,
        *,
        line_item_text: str,
        original_sector: str,
        final_sector: str,
        engagement_id: UUID,
        workspace_id: UUID,
        actor: UUID | None = None,
    ) -> MappingLibraryEntry:
        """HIGH VALUE: Add correction with final_sector.

        Override confidence is 0.9 — analyst corrections are strong signals.
        """
        entry = MappingLibraryEntry(
            workspace_id=workspace_id,
            pattern=line_item_text,
            sector_code=final_sector,
            confidence=0.9,
            source_engagement_id=engagement_id,
            created_by=actor,
            status=EntryStatus.DRAFT,
        )
        self._overrides_captured += 1
        return self._mapping_service.add_entry(entry)

    def on_assumption_approved(
        self,
        *,
        assumption_type: LibraryAssumptionType,
        sector_code: str,
        value: float,
        range_low: float,
        range_high: float,
        unit: str,
        engagement_id: UUID,
        workspace_id: UUID,
        confidence: ConstraintConfidence = ConstraintConfidence.ESTIMATED,
        actor: UUID | None = None,
    ) -> AssumptionLibraryEntry:
        """When an assumption passes manager review, add to library."""
        entry = AssumptionLibraryEntry(
            workspace_id=workspace_id,
            assumption_type=assumption_type,
            sector_code=sector_code,
            default_value=value,
            range_low=range_low,
            range_high=range_high,
            unit=unit,
            source="engagement",
            source_engagement_id=engagement_id,
            confidence=confidence,
            created_by=actor,
            status=EntryStatus.DRAFT,
        )
        return self._assumption_service.add_entry(entry)

    def on_engagement_completed(
        self,
        *,
        engagement_id: UUID,
        workspace_id: UUID,
        sector_codes: list[str],
        shock_types: list[str],
    ) -> ScenarioPattern | None:
        """Extract pattern from completed engagement.

        Requires >= 2 sectors + >= 1 shock type to be worth extracting.
        """
        if len(sector_codes) < 2 or len(shock_types) < 1:
            return None

        pattern = ScenarioPattern(
            workspace_id=workspace_id,
            name=f"Engagement {str(engagement_id)[:8]}",
            sector_focus=sector_codes,
            typical_shock_types=shock_types,
            source_engagement_ids=[engagement_id],
        )
        return self._pattern_service.add_pattern(pattern)

    def get_growth_metrics(self) -> dict:
        """Return library growth metrics."""
        return {
            "mapping_entries": len(self._mapping_service._entries),
            "assumption_entries": len(self._assumption_service._entries),
            "scenario_patterns": len(self._pattern_service._patterns),
            "overrides_captured": self._overrides_captured,
        }
