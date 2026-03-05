"""Export model — governed report pack generation."""

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from src.models.common import (
    DisclosureTier,
    ExportMode,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


class ExportStatus(StrEnum):
    """Lifecycle status for an export artifact."""

    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class Export(ImpactOSBase):
    """Export artifact representing a generated Decision Pack.

    Governed exports require NFF pass: approved assumptions, resolved claims,
    locked mappings, and a valid RunSnapshot.
    """

    export_id: UUIDv7 = Field(default_factory=new_uuid7)
    run_id: UUID
    template_version: str = Field(..., min_length=1, max_length=100)
    mode: ExportMode = Field(default=ExportMode.SANDBOX)
    disclosure_tier: DisclosureTier = Field(default=DisclosureTier.TIER0)
    status: ExportStatus = Field(default=ExportStatus.PENDING)
    checksum: str | None = Field(
        default=None,
        pattern=r"^sha256:[a-f0-9]{64}$",
        description="SHA-256 hash of the generated export artifact.",
    )
    blocked_reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable reasons if export is blocked by governance.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)


class BridgeReasonCode(StrEnum):
    """Reason codes for invalid bridge requests."""

    BRIDGE_RUN_NOT_FOUND = "BRIDGE_RUN_NOT_FOUND"
    BRIDGE_NO_RESULTS = "BRIDGE_NO_RESULTS"
    BRIDGE_SAME_RUN = "BRIDGE_SAME_RUN"
    BRIDGE_INCOMPATIBLE_RUNS = "BRIDGE_INCOMPATIBLE_RUNS"
    BRIDGE_NOT_FOUND = "BRIDGE_NOT_FOUND"


class VarianceBridgeAnalysis(ImpactOSBase):
    """Persisted variance bridge analysis record."""

    analysis_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    run_a_id: UUID
    run_b_id: UUID
    metric_type: str = Field(default="total_output", min_length=1, max_length=100)
    analysis_version: str = Field(default="bridge_v1", max_length=50)
    config_json: dict = Field(default_factory=dict)
    config_hash: str = Field(..., pattern=r"^sha256:[a-f0-9]{64}$")
    result_json: dict = Field(default_factory=dict)
    result_checksum: str = Field(..., pattern=r"^sha256:[a-f0-9]{64}$")
    created_at: UTCTimestamp = Field(default_factory=utc_now)
