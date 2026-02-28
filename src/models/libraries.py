"""Knowledge Flywheel Pydantic models — MVP-12.

Models for the three libraries (mapping, assumption, scenario pattern),
library stats, and override accuracy reporting.

All 8 amendments enforced:
- Amendment 1: Version UniqueConstraint = (workspace_id, version)
- Amendment 2: Entry content-immutable; only usage_count/last_used_at/status mutable
- Amendment 5: CalibrationNotes/EngagementInsights deferred
- Amendment 6: evidence_refs on AssumptionLibraryEntry
- Amendment 7: Entry status DRAFT/PUBLISHED/DEPRECATED
- Amendment 8: Scoring guardrails in _text_utils.py
"""

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import (
    ConstraintConfidence,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LibraryAssumptionType(StrEnum):
    """Extended assumption type for library entries.

    Superset of common.AssumptionType + LOCAL_CONTENT + OTHER.
    """

    IMPORT_SHARE = "IMPORT_SHARE"
    PHASING = "PHASING"
    DEFLATOR = "DEFLATOR"
    WAGE_PROXY = "WAGE_PROXY"
    CAPACITY_CAP = "CAPACITY_CAP"
    JOBS_COEFF = "JOBS_COEFF"
    LOCAL_CONTENT = "LOCAL_CONTENT"
    OTHER = "OTHER"


class EntryStatus(StrEnum):
    """Amendment 7: Steward-gated entry lifecycle.

    DRAFT — auto-captured or manually added, not yet reviewed.
    PUBLISHED — steward-promoted, included in published versions.
    DEPRECATED — replaced or invalidated.
    """

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"


# ---------------------------------------------------------------------------
# Mapping Library
# ---------------------------------------------------------------------------


class MappingLibraryEntry(ImpactOSBase):
    """Enhanced mapping library entry with provenance and status.

    Content fields (pattern, sector_code, confidence, tags) are FROZEN after
    creation per Amendment 2. Only usage_count, last_used_at, and status
    may be updated.
    """

    entry_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    pattern: str = Field(..., min_length=1, max_length=500)
    sector_code: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    usage_count: int = Field(default=0, ge=0)
    source_engagement_id: UUID | None = None
    last_used_at: UTCTimestamp | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: UUID | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    status: EntryStatus = Field(default=EntryStatus.DRAFT)


class MappingLibraryVersion(ImpactOSBase, frozen=True):
    """Immutable snapshot of published mapping library entries.

    Business key: (workspace_id, version) per Amendment 1.
    Only entries with status=PUBLISHED are included per Amendment 7.
    """

    library_version_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    version: int = Field(default=1, ge=1)
    entry_ids: list[UUID] = Field(default_factory=list)
    entry_count: int = Field(default=0, ge=0)
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    published_by: UUID | None = None


# ---------------------------------------------------------------------------
# Assumption Library
# ---------------------------------------------------------------------------


class AssumptionLibraryEntry(ImpactOSBase):
    """Sector-level default assumption with range.

    Content-immutable after creation per Amendment 2.
    evidence_refs for NFF alignment per Amendment 6.
    Entry status per Amendment 7.
    """

    entry_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    assumption_type: LibraryAssumptionType
    sector_code: str = Field(..., min_length=1)
    default_value: float
    range_low: float
    range_high: float
    unit: str = Field(..., min_length=1, max_length=50)
    justification: str = Field(default="")
    source: str = Field(default="")
    source_engagement_id: UUID | None = None
    usage_count: int = Field(default=0, ge=0)
    last_used_at: UTCTimestamp | None = None
    confidence: ConstraintConfidence = Field(
        default=ConstraintConfidence.ASSUMED,
    )
    created_by: UUID | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    evidence_refs: list[UUID] = Field(default_factory=list)
    status: EntryStatus = Field(default=EntryStatus.DRAFT)

    @model_validator(mode="after")
    def _range_valid(self) -> "AssumptionLibraryEntry":
        if self.range_high < self.range_low:
            msg = "range_high must be >= range_low"
            raise ValueError(msg)
        return self


class AssumptionLibraryVersion(ImpactOSBase, frozen=True):
    """Immutable snapshot of published assumption library entries.

    Business key: (workspace_id, version) per Amendment 1.
    """

    library_version_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    version: int = Field(default=1, ge=1)
    entry_ids: list[UUID] = Field(default_factory=list)
    entry_count: int = Field(default=0, ge=0)
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    published_by: UUID | None = None


# ---------------------------------------------------------------------------
# Scenario Pattern
# ---------------------------------------------------------------------------


class ScenarioPattern(ImpactOSBase):
    """Reusable scenario template from engagement learnings."""

    pattern_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="")
    sector_focus: list[str] = Field(default_factory=list)
    typical_shock_types: list[str] = Field(default_factory=list)
    typical_assumptions: list[dict] = Field(default_factory=list)
    recommended_sensitivities: list[str] = Field(default_factory=list)
    recommended_contrarian_angles: list[str] = Field(default_factory=list)
    source_engagement_ids: list[UUID] = Field(default_factory=list)
    usage_count: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)
    created_by: UUID | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Output / Reporting Models
# ---------------------------------------------------------------------------


class LibraryStats(ImpactOSBase):
    """Aggregate statistics for a library."""

    total_entries: int = Field(default=0, ge=0)
    total_versions: int = Field(default=0, ge=0)
    total_usage: int = Field(default=0, ge=0)
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    top_sectors: list[str] = Field(default_factory=list)


class OverrideAccuracyReport(ImpactOSBase):
    """Override tracker accuracy report."""

    total_suggestions: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    overridden_count: int = Field(default=0, ge=0)
    accuracy_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    by_sector: dict[str, dict] = Field(default_factory=dict)
    high_confidence_overrides: list[dict] = Field(default_factory=list)
