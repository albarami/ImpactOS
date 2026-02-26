"""Run models — RunRequest, RunSnapshot (immutable), ResultSet (immutable)."""

from uuid import UUID

from pydantic import Field

from src.models.common import ExportMode, ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now


class RunRequest(ImpactOSBase):
    """Request to execute a scenario run per Section 6.3.2."""

    run_id: UUIDv7 = Field(default_factory=new_uuid7)
    scenario_spec_id: UUID
    scenario_spec_version: int = Field(..., ge=1)
    mode: ExportMode = Field(default=ExportMode.SANDBOX)
    sensitivity_plan_id: UUID | None = None
    export_template_version: str | None = None
    requested_outputs: list[str] = Field(default_factory=list)
    created_at: UTCTimestamp = Field(default_factory=utc_now)


class RunSnapshot(ImpactOSBase, frozen=True):
    """Immutable snapshot of all version references at run time.

    Captures everything needed for exact reproducibility years later.
    """

    run_id: UUID
    model_version_id: UUID
    taxonomy_version_id: UUID
    concordance_version_id: UUID
    mapping_library_version_id: UUID
    assumption_library_version_id: UUID
    prompt_pack_version_id: UUID
    constraint_set_version_id: UUID | None = None
    source_checksums: list[str] = Field(default_factory=list)
    created_at: UTCTimestamp = Field(default_factory=utc_now)


class ResultSet(ImpactOSBase, frozen=True):
    """Immutable deterministic engine output per Section 5.3.

    Authoritative source of all numerical results. Generated only
    by the deterministic engine — never by AI components.
    """

    result_id: UUIDv7 = Field(default_factory=new_uuid7)
    run_id: UUID
    metric_type: str = Field(..., min_length=1)
    values: dict[str, float] = Field(
        ...,
        description="Metric values keyed by sector code or aggregate label.",
    )
    sector_breakdowns: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Nested breakdowns: outer key = breakdown type, inner = sector → value.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)
