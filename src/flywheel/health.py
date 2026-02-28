"""Flywheel health metrics (Task 16, Amendment 10).

Provides:
- ``FlywheelHealth``: overall health metrics for the Knowledge Flywheel
- ``FlywheelHealthService``: computes health metrics from all flywheel components

Per MVP-12 design doc and Amendment 10 (backlog metrics).
"""

from __future__ import annotations

from datetime import datetime

from src.flywheel.assumption_library import AssumptionLibraryManager
from src.flywheel.calibration import CalibrationNoteStore
from src.flywheel.engagement_memory import EngagementMemoryStore
from src.flywheel.mapping_library import MappingLibraryManager
from src.flywheel.scenario_patterns import ScenarioPatternLibrary
from src.flywheel.workforce_refinement import WorkforceBridgeRefinement
from src.models.common import ImpactOSBase, UTCTimestamp, utc_now


class FlywheelHealth(ImpactOSBase):
    """Overall health metrics for the Knowledge Flywheel (Amendment 10)."""

    total_engagements: int = 0

    # Mapping library
    mapping_library_version: int = 0
    mapping_entry_count: int = 0
    mapping_accuracy: float | None = None

    # Assumption library
    assumption_default_count: int = 0
    assumption_library_version: int = 0

    # Scenario patterns
    scenario_pattern_count: int = 0

    # Calibration
    calibration_note_count: int = 0

    # Engagement memory
    engagement_memory_count: int = 0

    # Workforce
    workforce_coverage_pct: float = 0.0  # % of cells calibrated

    # Backlog metrics (Amendment 10)
    override_backlog_count: int = 0
    avg_days_since_last_publication: float = 0.0
    draft_count_pending_review: int = 0
    pct_entries_assumed_vs_calibrated: float = 0.0
    pct_shared_knowledge_sanitized: float = 0.0
    last_publication: UTCTimestamp | None = None


class FlywheelHealthService:
    """Computes health metrics from all flywheel components."""

    def __init__(
        self,
        mapping_manager: MappingLibraryManager,
        assumption_manager: AssumptionLibraryManager,
        pattern_library: ScenarioPatternLibrary,
        calibration_store: CalibrationNoteStore,
        memory_store: EngagementMemoryStore,
        workforce_refinement: WorkforceBridgeRefinement,
    ) -> None:
        self._mapping_manager = mapping_manager
        self._assumption_manager = assumption_manager
        self._pattern_library = pattern_library
        self._calibration_store = calibration_store
        self._memory_store = memory_store
        self._workforce_refinement = workforce_refinement

    def compute_health(self) -> FlywheelHealth:
        """Compute current health metrics from all components.

        Logic:
        - mapping_library_version: active version's version_number (0 if none)
        - mapping_entry_count: active version's entry_count (0 if none)
        - mapping_accuracy: active version's accuracy_at_publish
        - assumption_default_count: active version's default_count
        - assumption_library_version: active version's version_number
        - scenario_pattern_count: len(pattern_library.find_patterns())
        - calibration_note_count: len(calibration_store.list_all())
        - engagement_memory_count: len(memory_store.list_all())
        - workforce_coverage_pct: from workforce_refinement.get_refinement_coverage()
          - If total_cells > 0: engagement_calibrated_cells / total_cells * 100
          - If total_cells == 0: 0.0
        - last_publication: latest published_at from mapping or assumption active version
        """
        # Mapping library metrics
        mapping_version = self._mapping_manager.get_active_version()
        mapping_library_version = 0
        mapping_entry_count = 0
        mapping_accuracy: float | None = None
        mapping_published_at: datetime | None = None

        if mapping_version is not None:
            mapping_library_version = mapping_version.version_number
            mapping_entry_count = mapping_version.entry_count
            mapping_accuracy = mapping_version.accuracy_at_publish
            mapping_published_at = mapping_version.published_at

        # Assumption library metrics
        assumption_version = self._assumption_manager.get_active_version()
        assumption_default_count = 0
        assumption_library_version = 0
        assumption_published_at: datetime | None = None

        if assumption_version is not None:
            assumption_default_count = assumption_version.default_count
            assumption_library_version = assumption_version.version_number
            assumption_published_at = assumption_version.published_at

        # Scenario patterns
        scenario_pattern_count = len(self._pattern_library.find_patterns())

        # Calibration notes
        calibration_note_count = len(self._calibration_store.list_all())

        # Engagement memories
        engagement_memory_count = len(self._memory_store.list_all())

        # Workforce coverage
        coverage = self._workforce_refinement.get_refinement_coverage()
        total_cells = coverage["total_cells"]
        calibrated_cells = coverage["engagement_calibrated_cells"]
        if total_cells > 0:
            workforce_coverage_pct = calibrated_cells / total_cells * 100.0
        else:
            workforce_coverage_pct = 0.0

        # Last publication: latest published_at from mapping or assumption
        last_publication: datetime | None = None
        candidates: list[datetime] = []
        if mapping_published_at is not None:
            candidates.append(mapping_published_at)
        if assumption_published_at is not None:
            candidates.append(assumption_published_at)
        if candidates:
            last_publication = max(candidates)

        # ----- Backlog metrics (Amendment 10) -----

        # override_backlog_count: requires tracking which overrides have been
        # published into a library version vs. which are still pending.
        # Deferred — requires draft store and override-to-published tracking.
        override_backlog_count = 0

        # avg_days_since_last_publication: computed from last_publication
        if last_publication is not None:
            avg_days_since_last_publication = (
                utc_now() - last_publication
            ).total_seconds() / 86400.0
        else:
            avg_days_since_last_publication = 0.0

        # draft_count_pending_review: requires a draft store that tracks
        # in-progress drafts across all libraries.
        # Deferred — requires draft store.
        draft_count_pending_review = 0

        # pct_entries_assumed_vs_calibrated: requires knowing which library
        # entries are calibrated (backed by analyst override data) vs.
        # assumed (seeded without override evidence).
        # Deferred — requires calibration metadata on library entries.
        pct_entries_assumed_vs_calibrated = 0.0

        # pct_shared_knowledge_sanitized: requires tracking which entries
        # have been reviewed/sanitized for cross-workspace sharing.
        # Deferred — requires sanitization metadata on library entries.
        pct_shared_knowledge_sanitized = 0.0

        return FlywheelHealth(
            mapping_library_version=mapping_library_version,
            mapping_entry_count=mapping_entry_count,
            mapping_accuracy=mapping_accuracy,
            assumption_default_count=assumption_default_count,
            assumption_library_version=assumption_library_version,
            scenario_pattern_count=scenario_pattern_count,
            calibration_note_count=calibration_note_count,
            engagement_memory_count=engagement_memory_count,
            workforce_coverage_pct=workforce_coverage_pct,
            last_publication=last_publication,
            override_backlog_count=override_backlog_count,
            avg_days_since_last_publication=avg_days_since_last_publication,
            draft_count_pending_review=draft_count_pending_review,
            pct_entries_assumed_vs_calibrated=pct_entries_assumed_vs_calibrated,
            pct_shared_knowledge_sanitized=pct_shared_knowledge_sanitized,
        )
