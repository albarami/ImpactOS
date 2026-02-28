"""Calibration notes for the Knowledge Flywheel (Task 10).

Calibration notes document observations about model accuracy — where
multipliers, coefficients, or ratios diverged from real-world outcomes.
They feed the flywheel by capturing empirical corrections that can later
be promoted into assumption defaults.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from src.flywheel.models import PromotionStatus, ReuseScopeLevel
from src.flywheel.stores import InMemoryAppendOnlyStore
from src.models.common import ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now


class CalibrationNote(ImpactOSBase):
    """Documented observation about model accuracy.

    Example: "Construction multiplier in 2024 NEOM engagement overstated
    employment by ~15% vs GOSI actual data."
    """

    note_id: UUIDv7 = Field(default_factory=new_uuid7)
    sector_code: str | None = None
    engagement_id: UUID | None = None
    observation: str
    likely_cause: str
    recommended_adjustment: str | None = None
    metric_affected: str  # "employment", "output_multiplier", "import_ratio"
    direction: str  # "overstate" or "understate"
    magnitude_estimate: float | None = None  # Approximate error %
    created_by: UUID
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    validated: bool = False
    # Promotion path (Amendment 8)
    promoted_to: UUID | None = None  # assumption_default_id if promoted
    promotion_status: PromotionStatus = PromotionStatus.RAW
    # Scope (Amendment 1)
    workspace_id: UUID
    source_engagement_id: UUID | None = None
    reuse_scope: ReuseScopeLevel = ReuseScopeLevel.WORKSPACE_ONLY
    sanitized_for_promotion: bool = False


class CalibrationNoteStore(InMemoryAppendOnlyStore[CalibrationNote]):
    """In-memory store for calibration notes with search methods."""

    def __init__(self) -> None:
        super().__init__(id_field="note_id")

    def find_by_sector(self, sector_code: str) -> list[CalibrationNote]:
        """Search by sector code."""
        return [n for n in self._items if n.sector_code == sector_code]

    def find_by_metric(self, metric_affected: str) -> list[CalibrationNote]:
        """Search by metric."""
        return [n for n in self._items if n.metric_affected == metric_affected]

    def find_by_engagement(self, engagement_id: UUID) -> list[CalibrationNote]:
        """Search by engagement."""
        return [n for n in self._items if n.engagement_id == engagement_id]

    def find_validated(self) -> list[CalibrationNote]:
        """Return only validated notes."""
        return [n for n in self._items if n.validated]

    def find_unvalidated(self) -> list[CalibrationNote]:
        """Return only unvalidated notes."""
        return [n for n in self._items if not n.validated]
