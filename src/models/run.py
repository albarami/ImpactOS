"""Run models — RunRequest, RunSnapshot (immutable), ResultSet (immutable)."""

from uuid import UUID

from pydantic import Field, model_validator

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
    # Amendment 5: workforce version references
    occupation_bridge_version_id: UUID | None = None
    nationality_classification_version_id: UUID | None = None
    nitaqat_target_version_id: UUID | None = None
    source_checksums: list[str] = Field(default_factory=list)
    # D-5 Task 8: Provenance badge — records which data path the run used
    data_mode: str | None = None           # "curated_real" | "curated_estimated" | "synthetic_fallback" | "synthetic_only"
    data_source_id: str | None = None      # manifest dataset_id
    checksum_verified: bool = False
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
    # Sprint 17: annual time-series storage fields
    year: int | None = None
    series_kind: str | None = None
    baseline_run_id: UUID | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_series_fields(self) -> "ResultSet":
        _VALID_SERIES_KINDS = {"annual", "peak", "delta"}

        if self.series_kind is not None and self.series_kind not in _VALID_SERIES_KINDS:
            raise ValueError(
                f"series_kind must be one of {_VALID_SERIES_KINDS}, got {self.series_kind!r}"
            )

        if self.series_kind is not None and self.year is None:
            raise ValueError("year is required when series_kind is set")

        if self.series_kind is None and self.year is not None:
            raise ValueError("year must be None when series_kind is None (legacy row)")

        if self.series_kind == "delta" and self.baseline_run_id is None:
            raise ValueError("baseline_run_id is required when series_kind='delta'")

        if self.series_kind != "delta" and self.baseline_run_id is not None:
            raise ValueError("baseline_run_id must be None unless series_kind='delta'")

        return self
