"""SQLAlchemy ORM table models for ImpactOS.

All 22 tables defined in a single file. Uses FlexJSON (JSONB on Postgres,
JSON on SQLite) for complex nested types.

Categories:
- IMMUTABLE: ModelVersion, ModelData, RunSnapshot, ResultSet, EvidenceSnippet,
             ScenarioSpec (append-only versioned rows)
- OPERATIONAL: ExtractionJob, Export, Batch, Claim, MappingDecision,
               Assumption (status updates allowed)
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from src.db.session import Base

# JSONB on PostgreSQL, plain JSON on SQLite (for tests)
FlexJSON = JSONB().with_variant(JSON(), "sqlite")


# ---------------------------------------------------------------------------
# Foundation
# ---------------------------------------------------------------------------


class WorkspaceRow(Base):
    __tablename__ = "workspaces"

    workspace_id: Mapped[UUID] = mapped_column(primary_key=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    engagement_code: Mapped[str] = mapped_column(String(100), nullable=False)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Engine — IMMUTABLE
# ---------------------------------------------------------------------------


class ModelVersionRow(Base):
    """Immutable I-O model metadata."""

    __tablename__ = "model_versions"

    model_version_id: Mapped[UUID] = mapped_column(primary_key=True)
    base_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    sector_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelDataRow(Base):
    """Immutable model matrix data. Linked 1:1 to ModelVersionRow.

    storage_format: 'json' (current), future: 'compressed_binary', 'object_ref'.
    """

    __tablename__ = "model_data"

    model_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_versions.model_version_id"), primary_key=True
    )
    z_matrix_json = mapped_column(FlexJSON, nullable=False)
    x_vector_json = mapped_column(FlexJSON, nullable=False)
    sector_codes = mapped_column(FlexJSON, nullable=False)
    storage_format: Mapped[str] = mapped_column(String(50), default="json", nullable=False)


class RunSnapshotRow(Base):
    """Immutable snapshot of all version references at run time."""

    __tablename__ = "run_snapshots"

    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    model_version_id: Mapped[UUID] = mapped_column(nullable=False)
    taxonomy_version_id: Mapped[UUID] = mapped_column(nullable=False)
    concordance_version_id: Mapped[UUID] = mapped_column(nullable=False)
    mapping_library_version_id: Mapped[UUID] = mapped_column(nullable=False)
    assumption_library_version_id: Mapped[UUID] = mapped_column(nullable=False)
    prompt_pack_version_id: Mapped[UUID] = mapped_column(nullable=False)
    constraint_set_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_checksums = mapped_column(FlexJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResultSetRow(Base):
    """Immutable engine output — metric values and sector breakdowns."""

    __tablename__ = "result_sets"

    result_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False)
    values = mapped_column(FlexJSON, nullable=False)
    sector_breakdowns = mapped_column(FlexJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BatchRow(Base):
    __tablename__ = "batches"

    batch_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_ids = mapped_column(FlexJSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="COMPLETED", nullable=False)
    workspace_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Scenarios — VERSIONED (surrogate PK)
# ---------------------------------------------------------------------------


class ScenarioSpecRow(Base):
    """Append-only versioned scenario spec. Surrogate PK (row_id)."""

    __tablename__ = "scenario_specs"
    __table_args__ = (
        UniqueConstraint("scenario_spec_id", "version", name="uq_scenario_spec_version"),
    )

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_spec_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    disclosure_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    base_model_version_id: Mapped[UUID] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)
    base_year: Mapped[int] = mapped_column(Integer, nullable=False)
    time_horizon = mapped_column(FlexJSON, nullable=False)
    shock_items = mapped_column(FlexJSON, nullable=False)
    assumption_ids = mapped_column(FlexJSON, nullable=False)
    data_quality_summary = mapped_column(FlexJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentRow(Base):
    __tablename__ = "documents"

    doc_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)


class ExtractionJobRow(Base):
    """Operational — status transitions allowed."""

    __tablename__ = "extraction_jobs"

    job_id: Mapped[UUID] = mapped_column(primary_key=True)
    doc_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    extract_tables: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extract_line_items: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    language_hint: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LineItemRow(Base):
    __tablename__ = "line_items"

    line_item_id: Mapped[UUID] = mapped_column(primary_key=True)
    doc_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    extraction_job_id: Mapped[UUID] = mapped_column(nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency_code: Mapped[str] = mapped_column(String(10), default="SAR", nullable=False)
    year_or_phase: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    page_ref: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_snippet_ids = mapped_column(FlexJSON, nullable=False)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------


class EvidenceSnippetRow(Base):
    """Immutable — audit-grade source reference with bounding box."""

    __tablename__ = "evidence_snippets"

    snippet_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x0: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y0: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x1: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y1: Mapped[float] = mapped_column(Float, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    table_cell_ref = mapped_column(FlexJSON, nullable=True)
    checksum: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssumptionRow(Base):
    """Operational — status transitions (DRAFT → APPROVED/REJECTED)."""

    __tablename__ = "assumptions"

    assumption_id: Mapped[UUID] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    range_json = mapped_column(FlexJSON, nullable=True)
    units: Mapped[str] = mapped_column(String(50), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs = mapped_column(FlexJSON, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    approved_by: Mapped[UUID | None] = mapped_column(nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssumptionLinkRow(Base):
    __tablename__ = "assumption_links"
    __table_args__ = (
        UniqueConstraint("assumption_id", "target_id", "link_type", name="uq_assumption_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assumption_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)


class ClaimRow(Base):
    """Operational — status transitions through governance lifecycle."""

    __tablename__ = "claims"

    claim_id: Mapped[UUID] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    disclosure_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    model_refs = mapped_column(FlexJSON, nullable=False)
    evidence_refs = mapped_column(FlexJSON, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Mapping — OPERATIONAL (7-state machine)
# ---------------------------------------------------------------------------


class MappingDecisionRow(Base):
    """Operational — state machine transitions for HITL reconciliation."""

    __tablename__ = "mapping_decisions"

    mapping_decision_id: Mapped[UUID] = mapped_column(primary_key=True)
    line_item_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    scenario_spec_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    suggested_sector_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suggested_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_sector_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[UUID] = mapped_column(nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


class CompilationRow(Base):
    __tablename__ = "compilations"

    compilation_id: Mapped[UUID] = mapped_column(primary_key=True)
    result_json = mapped_column(FlexJSON, nullable=False)
    metadata_json = mapped_column(FlexJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OverridePairRow(Base):
    """Learning loop: analyst override pairs for mapping improvement."""

    __tablename__ = "override_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    override_id: Mapped[UUID] = mapped_column(unique=True, nullable=False)
    engagement_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    line_item_id: Mapped[UUID] = mapped_column(nullable=False)
    line_item_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_sector_code: Mapped[str] = mapped_column(String(100), nullable=False)
    final_sector_code: Mapped[str] = mapped_column(String(100), nullable=False)
    project_type: Mapped[str] = mapped_column(String(200), default="")
    actor: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Export — OPERATIONAL
# ---------------------------------------------------------------------------


class ExportRow(Base):
    """Operational — status transitions (PENDING → GENERATING → COMPLETED/FAILED/BLOCKED)."""

    __tablename__ = "exports"

    export_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    disclosure_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checksums_json = mapped_column(FlexJSON, nullable=True)
    blocked_reasons = mapped_column(FlexJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


class MetricEventRow(Base):
    __tablename__ = "metric_events"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    engagement_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[UUID | None] = mapped_column(nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json = mapped_column(FlexJSON, nullable=True)


class EngagementRow(Base):
    __tablename__ = "engagements"

    engagement_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    current_phase: Mapped[str] = mapped_column(String(50), nullable=False)
    phase_transitions = mapped_column(FlexJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Depth Engine — Al-Muhasabi 5-step reasoning
# ---------------------------------------------------------------------------


class DepthPlanRow(Base):
    """Operational — status transitions through depth engine pipeline."""

    __tablename__ = "depth_plans"

    plan_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    scenario_spec_id: Mapped[UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(50), nullable=True)
    degraded_steps = mapped_column(FlexJSON, nullable=False)
    step_errors = mapped_column(FlexJSON, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DepthArtifactRow(Base):
    """Per-step artifact from the depth engine. One artifact per (plan, step).

    payload stores the serialized typed output (FlexJSON).
    metadata stores LLM audit info (provider, model, generation_mode, etc.).
    """

    __tablename__ = "depth_artifacts"
    __table_args__ = (
        UniqueConstraint("plan_id", "step", name="uq_depth_artifact_plan_step"),
    )

    artifact_id: Mapped[UUID] = mapped_column(primary_key=True)
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("depth_plans.plan_id"), nullable=False, index=True,
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    payload = mapped_column(FlexJSON, nullable=False)
    disclosure_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_json = mapped_column(FlexJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
