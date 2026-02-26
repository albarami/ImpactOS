"""Export model — governed report pack generation."""

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from src.models.common import DisclosureTier, ExportMode, ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now


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
