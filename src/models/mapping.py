"""Mapping models — MappingDecision, MappingLibraryEntry (MVP-4).

Per tech spec Section 9 and data spec Section 3.3.3.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now


class DecisionType(StrEnum):
    """HITL mapping decision types per Section 3.3.3."""

    APPROVED = "APPROVED"
    OVERRIDDEN = "OVERRIDDEN"
    DEFERRED = "DEFERRED"
    EXCLUDED = "EXCLUDED"


class MappingDecision(ImpactOSBase):
    """Analyst decision on a line-item-to-sector mapping.

    Captures suggested mapping (from AI or library), final decision,
    and full audit trail per Section 3.3.3.
    """

    mapping_decision_id: UUIDv7 = Field(default_factory=new_uuid7)
    line_item_id: UUID
    suggested_sector_code: str | None = None
    suggested_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    final_sector_code: str | None = None
    decision_type: DecisionType
    decision_note: str | None = None
    decided_by: UUID
    decided_at: UTCTimestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _approved_requires_final_sector(self) -> "MappingDecision":
        if self.decision_type in (DecisionType.APPROVED, DecisionType.OVERRIDDEN):
            if not self.final_sector_code:
                msg = "final_sector_code is required for APPROVED/OVERRIDDEN decisions."
                raise ValueError(msg)
        return self


class MappingLibraryEntry(ImpactOSBase):
    """Reusable mapping pattern: procurement text → sector code.

    Used to pre-populate suggestions for common line items (Section 9.6).
    """

    entry_id: UUIDv7 = Field(default_factory=new_uuid7)
    pattern: str = Field(..., min_length=1, max_length=500)
    sector_code: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    usage_count: int = Field(default=0, ge=0)
    created_at: UTCTimestamp = Field(default_factory=utc_now)
