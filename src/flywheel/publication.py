"""Publication service and quality gates for the Knowledge Flywheel.

Provides:
- ``PublicationQualityGate``: gates that must pass before a draft can be
  published (Amendment 6) — steward review, duplicate check, conflict check
- ``PublicationResult``: result summary of a publication cycle
- ``FlywheelPublicationService``: orchestrates publication of new library
  versions, wiring together all flywheel components

Publication workflow:
1. Collect signals (overrides, calibration notes)
2. Build draft versions of each library
3. Review (quality gates)
4. Publish -> new versions become active
5. Old versions remain accessible for reproducibility

Per tech spec Section 9.6, MVP-12 design doc, and Amendment 6.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.compiler.learning import LearningLoop
from src.flywheel.assumption_library import (
    AssumptionLibraryDraft,
    AssumptionLibraryManager,
    AssumptionLibraryVersion,
)
from src.flywheel.mapping_library import (
    MappingLibraryDraft,
    MappingLibraryManager,
    MappingLibraryVersion,
)
from src.flywheel.scenario_patterns import ScenarioPatternLibrary
from src.flywheel.workforce_refinement import WorkforceBridgeRefinement
from src.models.common import ImpactOSBase, UTCTimestamp, utc_now


# ---------------------------------------------------------------------------
# Quality Gate model (Task 13)
# ---------------------------------------------------------------------------


class PublicationQualityGate(ImpactOSBase):
    """Gates that must pass before a draft can be published (Amendment 6).

    Validates mapping drafts against configurable checks:
    - Steward review requirement
    - Duplicate entry detection (same pattern + sector_code)
    - Conflicting entry detection (same pattern, different sector_code)
    """

    min_override_frequency: int = Field(default=2, ge=1)
    min_accuracy_delta: float = Field(default=0.0, ge=0.0)
    require_steward_review: bool = True
    duplicate_check: bool = True
    conflict_check: bool = True

    def validate_mapping_draft(
        self,
        draft: MappingLibraryDraft,
        steward_approved: bool = False,
    ) -> list[str]:
        """Return list of gate failure messages. Empty = all gates pass.

        Checks:
        1. If require_steward_review and not steward_approved -> failure
        2. If duplicate_check -> check for duplicate entries (same pattern + sector_code)
        3. If conflict_check -> check for conflicting entries (same pattern, different sector_code)

        Parameters
        ----------
        draft:
            The mapping draft to validate.
        steward_approved:
            Whether a steward has reviewed and approved the draft.

        Returns
        -------
        list[str]
            Gate failure messages. Empty list means all gates pass.
        """
        failures: list[str] = []

        # Gate 1: Steward review
        if self.require_steward_review and not steward_approved:
            failures.append(
                "Steward review required but not approved."
            )

        # Gate 2: Duplicate detection (same pattern + same sector_code)
        if self.duplicate_check:
            seen: Counter[tuple[str, str]] = Counter()
            for entry in draft.entries:
                key = (entry.pattern, entry.sector_code)
                seen[key] += 1
            for (pattern, sector), count in seen.items():
                if count > 1:
                    failures.append(
                        f"Duplicate entry detected: pattern='{pattern}', "
                        f"sector_code='{sector}' appears {count} times."
                    )

        # Gate 3: Conflict detection (same pattern, different sector_code)
        if self.conflict_check:
            pattern_sectors: dict[str, set[str]] = {}
            for entry in draft.entries:
                pattern_sectors.setdefault(entry.pattern, set()).add(
                    entry.sector_code
                )
            for pattern, sectors in pattern_sectors.items():
                if len(sectors) > 1:
                    sector_list = ", ".join(sorted(sectors))
                    failures.append(
                        f"Conflicting entries for pattern='{pattern}': "
                        f"mapped to sectors [{sector_list}]."
                    )

        return failures


# ---------------------------------------------------------------------------
# Publication Result model (Task 14)
# ---------------------------------------------------------------------------


class PublicationResult(ImpactOSBase):
    """Result of a publication cycle.

    Summarises what was published, how many patterns were added or
    updated, and the current workforce coverage.
    """

    mapping_version: MappingLibraryVersion | None = None
    assumption_version: AssumptionLibraryVersion | None = None
    new_patterns: int = 0
    updated_patterns: int = 0
    workforce_coverage: dict = Field(default_factory=dict)
    published_at: UTCTimestamp = Field(default_factory=utc_now)
    summary: str = ""


# ---------------------------------------------------------------------------
# Publication Service (Task 14)
# ---------------------------------------------------------------------------


class FlywheelPublicationService:
    """Orchestrates the publication of new library versions.

    Publication workflow:
    1. Collect signals (overrides, calibration notes)
    2. Build draft versions of each library
    3. Review (quality gates)
    4. Publish -> new versions become active
    5. Old versions remain accessible for reproducibility
    """

    def __init__(
        self,
        mapping_manager: MappingLibraryManager,
        assumption_manager: AssumptionLibraryManager,
        pattern_library: ScenarioPatternLibrary,
        workforce_refinement: WorkforceBridgeRefinement,
    ) -> None:
        self._mapping = mapping_manager
        self._assumption = assumption_manager
        self._patterns = pattern_library
        self._workforce = workforce_refinement

    def publish_new_cycle(
        self,
        published_by: UUID,
        include_overrides_since: datetime | None = None,
        learning_loop: LearningLoop | None = None,
        steward_approved: bool = True,
        quality_gate: PublicationQualityGate | None = None,
    ) -> PublicationResult:
        """Run a full publication cycle for all libraries.

        Steps:
        1. Build mapping draft (incorporating overrides from learning_loop if provided)
        2. Build assumption draft (from current active or empty)
        3. Validate drafts against quality gates
        4. Publish both if they have changes
        5. Get workforce coverage
        6. Return PublicationResult summary

        IDEMPOTENT: If no changes from current active version, don't publish.
        - Mapping: if draft has same entries as active, skip
        - Assumption: if draft has same defaults as active, skip

        Parameters
        ----------
        published_by:
            UUID of the user triggering this publication cycle.
        include_overrides_since:
            Timestamp filter for overrides (reserved for future use).
        learning_loop:
            If provided, extract new patterns and update confidences
            from recorded analyst overrides.
        steward_approved:
            Whether a steward has reviewed and approved the draft.
        quality_gate:
            If provided, validate the mapping draft. If any failures,
            don't publish the mapping draft (but still publish assumption
            if it has changes).

        Returns
        -------
        PublicationResult
            Summary of what was published.
        """
        new_patterns = 0
        updated_patterns = 0
        published_mapping: MappingLibraryVersion | None = None
        published_assumption: AssumptionLibraryVersion | None = None

        # ----- Step 1: Build mapping draft -----
        active_mapping = self._mapping.get_active_version()
        base_mapping_id = (
            active_mapping.version_id if active_mapping is not None else None
        )

        mapping_draft = self._mapping.build_draft(
            base_version_id=base_mapping_id,
            include_overrides_since=include_overrides_since,
            learning_loop=learning_loop,
        )

        # Count new/updated patterns from the draft
        new_patterns = len(mapping_draft.added_entry_ids)
        updated_patterns = len(mapping_draft.changed_entries)

        # ----- Step 2: Build assumption draft -----
        active_assumption = self._assumption.get_active_version()
        base_assumption_id = (
            active_assumption.version_id
            if active_assumption is not None
            else None
        )

        assumption_draft = self._assumption.build_draft(
            base_version_id=base_assumption_id,
        )

        # ----- Step 3: Validate mapping draft against quality gates -----
        mapping_gate_passed = True
        if quality_gate is not None:
            gate_failures = quality_gate.validate_mapping_draft(
                mapping_draft, steward_approved=steward_approved
            )
            if gate_failures:
                mapping_gate_passed = False

        # ----- Step 4: Publish if there are changes -----

        # Mapping: publish only if gate passed and content differs from active
        if mapping_gate_passed and not self._mapping_unchanged(
            mapping_draft, active_mapping
        ):
            published_mapping = self._mapping.publish(
                mapping_draft, published_by=published_by
            )

        # Assumption: publish if content differs from active
        if not self._assumption_unchanged(assumption_draft, active_assumption):
            published_assumption = self._assumption.publish(
                assumption_draft, published_by=published_by
            )

        # ----- Step 5: Get workforce coverage -----
        workforce_coverage = self._workforce.get_refinement_coverage()

        # ----- Step 6: Build summary -----
        summary_parts: list[str] = []
        if published_mapping is not None:
            summary_parts.append(
                f"Published mapping library v{published_mapping.version_number} "
                f"with {published_mapping.entry_count} entries "
                f"({new_patterns} new, {updated_patterns} updated)."
            )
        if published_assumption is not None:
            summary_parts.append(
                f"Published assumption library v{published_assumption.version_number} "
                f"with {published_assumption.default_count} defaults."
            )
        if not summary_parts:
            summary_parts.append("No changes to publish.")

        return PublicationResult(
            mapping_version=published_mapping,
            assumption_version=published_assumption,
            new_patterns=new_patterns,
            updated_patterns=updated_patterns,
            workforce_coverage=workforce_coverage,
            summary=" ".join(summary_parts),
        )

    def get_flywheel_health(self) -> dict:
        """Return basic health metrics.

        Full FlywheelHealth model is in health.py.

        Returns
        -------
        dict
            Health metrics including version info, pattern count,
            and workforce coverage.
        """
        active_mapping = self._mapping.get_active_version()
        active_assumption = self._assumption.get_active_version()

        return {
            "mapping_version": (
                active_mapping.version_number
                if active_mapping is not None
                else None
            ),
            "assumption_version": (
                active_assumption.version_number
                if active_assumption is not None
                else None
            ),
            "pattern_count": len(self._patterns.find_patterns()),
            "workforce_coverage": self._workforce.get_refinement_coverage(),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mapping_unchanged(
        draft: MappingLibraryDraft,
        active: MappingLibraryVersion | None,
    ) -> bool:
        """Check whether a mapping draft is identical to the active version.

        Compares by the set of (pattern, sector_code) pairs — if both have
        the same set of entries, the draft is considered unchanged.

        Parameters
        ----------
        draft:
            The mapping draft to compare.
        active:
            The currently active mapping version (or None).

        Returns
        -------
        bool
            True if the draft content is identical to the active version.
        """
        if active is None:
            # No active version — draft is "changed" only if it has entries
            return len(draft.entries) == 0

        # Compare entry sets by (entry_id) for exact identity,
        # falling back to (pattern, sector_code) for content-based comparison
        draft_keys = {
            (e.entry_id, e.pattern, e.sector_code, e.confidence)
            for e in draft.entries
        }
        active_keys = {
            (e.entry_id, e.pattern, e.sector_code, e.confidence)
            for e in active.entries
        }
        return draft_keys == active_keys

    @staticmethod
    def _assumption_unchanged(
        draft: AssumptionLibraryDraft,
        active: AssumptionLibraryVersion | None,
    ) -> bool:
        """Check whether an assumption draft is identical to the active version.

        Compares by the set of assumption_default_ids.

        Parameters
        ----------
        draft:
            The assumption draft to compare.
        active:
            The currently active assumption version (or None).

        Returns
        -------
        bool
            True if the draft content is identical to the active version.
        """
        if active is None:
            return len(draft.defaults) == 0

        draft_ids = {d.assumption_default_id for d in draft.defaults}
        active_ids = {d.assumption_default_id for d in active.defaults}
        return draft_ids == active_ids
