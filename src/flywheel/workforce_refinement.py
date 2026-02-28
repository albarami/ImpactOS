"""Workforce bridge refinement with versioned artifacts (Task 12, Amendment 4).

Provides:
- OccupationBridgeVersion: immutable published version of the occupation bridge
- NationalityClassificationVersion: immutable published version of nationality classifications
- WorkforceBridgeRefinement: manages improvement of workforce bridges across engagements
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from src.data.workforce.nationality_classification import (
    ClassificationOverride,
    NationalityClassificationSet,
)
from src.data.workforce.occupation_bridge import OccupationBridge
from src.models.common import ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now


class OccupationBridgeVersion(ImpactOSBase, frozen=True):
    """Immutable published version of the occupation bridge."""

    model_config = {
        **ImpactOSBase.model_config,
        "arbitrary_types_allowed": True,
    }

    version_id: UUIDv7 = Field(default_factory=new_uuid7)
    version_number: int
    published_at: UTCTimestamp = Field(default_factory=utc_now)
    bridge_data: OccupationBridge
    parent_version_id: UUID | None = None


class NationalityClassificationVersion(ImpactOSBase, frozen=True):
    """Immutable published version of nationality classifications."""

    model_config = {
        **ImpactOSBase.model_config,
        "arbitrary_types_allowed": True,
    }

    version_id: UUIDv7 = Field(default_factory=new_uuid7)
    version_number: int
    published_at: UTCTimestamp = Field(default_factory=utc_now)
    classifications: NationalityClassificationSet
    overrides_incorporated: list[UUID] = Field(default_factory=list)
    parent_version_id: UUID | None = None


class WorkforceBridgeRefinement:
    """Manages the improvement of workforce bridges across engagements."""

    def __init__(self) -> None:
        self._overrides: list[ClassificationOverride] = []
        self._override_engagement_map: dict[UUID, list[ClassificationOverride]] = {}

    def record_engagement_overrides(
        self,
        engagement_id: UUID,
        overrides: list[ClassificationOverride],
    ) -> None:
        """Record overrides from an engagement. Accumulates across engagements."""
        self._overrides.extend(overrides)
        self._override_engagement_map.setdefault(engagement_id, []).extend(overrides)

    def get_all_overrides(self) -> list[ClassificationOverride]:
        """Return all accumulated overrides."""
        return list(self._overrides)

    def get_refinement_coverage(self) -> dict:
        """Report which (sector, occupation) pairs have been refined.

        Returns:
            {
                "total_cells": int,  # Total unique (sector, occupation) pairs
                "assumed_cells": int,  # Cells NOT yet overridden
                "engagement_calibrated_cells": int,  # Cells that HAVE overrides
                "engagement_count": int,  # Number of engagements with overrides
                "cells_by_engagement": {engagement_id: [(sector, occupation), ...]}
            }

        Note: total_cells is calculated from the actual overrides seen.
        Since we don't have a full classification set to compare against,
        we count unique (sector, occupation) pairs from overrides as "calibrated"
        and report those counts.
        """
        # Collect unique (sector, occupation) pairs from all overrides
        all_cells: set[tuple[str, str]] = set()
        for override in self._overrides:
            all_cells.add((override.sector_code, override.occupation_code))

        calibrated_count = len(all_cells)

        # Build per-engagement cell breakdown
        cells_by_engagement: dict[UUID, list[tuple[str, str]]] = {}
        for eng_id, eng_overrides in self._override_engagement_map.items():
            eng_cells: list[tuple[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for override in eng_overrides:
                cell = (override.sector_code, override.occupation_code)
                if cell not in seen:
                    seen.add(cell)
                    eng_cells.append(cell)
            cells_by_engagement[eng_id] = eng_cells

        return {
            "total_cells": calibrated_count,
            "assumed_cells": 0,
            "engagement_calibrated_cells": calibrated_count,
            "engagement_count": len(self._override_engagement_map),
            "cells_by_engagement": cells_by_engagement,
        }

    def build_refined_classifications(
        self,
        base: NationalityClassificationSet,
    ) -> NationalityClassificationSet:
        """Apply all accumulated overrides to produce an improved classification set.

        Uses base.apply_overrides() which is the existing flywheel hook.
        """
        return base.apply_overrides(self._overrides)
