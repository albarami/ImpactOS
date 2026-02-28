"""Initial schema — all 20 tables.

Revision ID: 001
Revises:
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Foundation --
    op.create_table(
        "workspaces",
        sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("engagement_code", sa.String(100), nullable=False),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- Engine (IMMUTABLE) --
    op.create_table(
        "model_versions",
        sa.Column("model_version_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("base_year", sa.Integer, nullable=False),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("sector_count", sa.Integer, nullable=False),
        sa.Column("checksum", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "model_data",
        sa.Column("model_version_id", UUID(as_uuid=True),
                  sa.ForeignKey("model_versions.model_version_id"), primary_key=True),
        sa.Column("z_matrix_json", JSONB, nullable=False),
        sa.Column("x_vector_json", JSONB, nullable=False),
        sa.Column("sector_codes", JSONB, nullable=False),
        sa.Column("storage_format", sa.String(50), server_default="json", nullable=False),
    )

    op.create_table(
        "run_snapshots",
        sa.Column("run_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("model_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("taxonomy_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("concordance_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("mapping_library_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("assumption_library_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_pack_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("constraint_set_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_checksums", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "result_sets",
        sa.Column("result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("metric_type", sa.String(100), nullable=False),
        sa.Column("values", JSONB, nullable=False),
        sa.Column("sector_breakdowns", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "batches",
        sa.Column("batch_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_ids", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- Scenarios (VERSIONED) --
    op.create_table(
        "scenario_specs",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("scenario_spec_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("disclosure_tier", sa.String(20), nullable=False),
        sa.Column("base_model_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(3), server_default="SAR", nullable=False),
        sa.Column("base_year", sa.Integer, nullable=False),
        sa.Column("time_horizon", JSONB, nullable=False),
        sa.Column("shock_items", JSONB, nullable=False),
        sa.Column("assumption_ids", JSONB, nullable=False),
        sa.Column("data_quality_summary", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scenario_spec_id", "version", name="uq_scenario_spec_version"),
    )

    # -- Documents --
    op.create_table(
        "documents",
        sa.Column("doc_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("hash_sha256", sa.String(100), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("language", sa.String(20), server_default="en", nullable=False),
    )

    op.create_table(
        "extraction_jobs",
        sa.Column("job_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("extract_tables", sa.Boolean, server_default="true", nullable=False),
        sa.Column("extract_line_items", sa.Boolean, server_default="true", nullable=False),
        sa.Column("language_hint", sa.String(20), server_default="en", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "line_items",
        sa.Column("line_item_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("extraction_job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("unit", sa.String(100), nullable=True),
        sa.Column("unit_price", sa.Float, nullable=True),
        sa.Column("total_value", sa.Float, nullable=True),
        sa.Column("currency_code", sa.String(10), server_default="SAR", nullable=False),
        sa.Column("year_or_phase", sa.String(100), nullable=True),
        sa.Column("vendor", sa.String(500), nullable=True),
        sa.Column("category_code", sa.String(100), nullable=True),
        sa.Column("page_ref", sa.Integer, nullable=False),
        sa.Column("evidence_snippet_ids", JSONB, nullable=False),
        sa.Column("completeness_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- Governance --
    op.create_table(
        "evidence_snippets",
        sa.Column("snippet_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("bbox_x0", sa.Float, nullable=False),
        sa.Column("bbox_y0", sa.Float, nullable=False),
        sa.Column("bbox_x1", sa.Float, nullable=False),
        sa.Column("bbox_y1", sa.Float, nullable=False),
        sa.Column("extracted_text", sa.Text, nullable=False),
        sa.Column("table_cell_ref", JSONB, nullable=True),
        sa.Column("checksum", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "assumptions",
        sa.Column("assumption_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("range_json", JSONB, nullable=True),
        sa.Column("units", sa.String(50), nullable=False),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column("evidence_refs", JSONB, nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "assumption_links",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("assumption_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(20), nullable=False),
        sa.UniqueConstraint("assumption_id", "target_id", "link_type", name="uq_assumption_link"),
    )

    op.create_table(
        "claims",
        sa.Column("claim_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("claim_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("disclosure_tier", sa.String(20), nullable=False),
        sa.Column("model_refs", JSONB, nullable=False),
        sa.Column("evidence_refs", JSONB, nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- Mapping --
    op.create_table(
        "mapping_decisions",
        sa.Column("mapping_decision_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("line_item_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("scenario_spec_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("suggested_sector_code", sa.String(100), nullable=True),
        sa.Column("suggested_confidence", sa.Float, nullable=True),
        sa.Column("final_sector_code", sa.String(100), nullable=True),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("decision_type", sa.String(50), nullable=True),
        sa.Column("decision_note", sa.Text, nullable=True),
        sa.Column("decided_by", UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- Compiler --
    op.create_table(
        "compilations",
        sa.Column("compilation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("result_json", JSONB, nullable=False),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "override_pairs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("override_id", UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column("engagement_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("line_item_id", UUID(as_uuid=True), nullable=False),
        sa.Column("line_item_text", sa.Text, nullable=False),
        sa.Column("suggested_sector_code", sa.String(100), nullable=False),
        sa.Column("final_sector_code", sa.String(100), nullable=False),
        sa.Column("project_type", sa.String(200), server_default=""),
        sa.Column("actor", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- Export --
    op.create_table(
        "exports",
        sa.Column("export_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("template_version", sa.String(100), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("disclosure_tier", sa.String(20), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("checksum", sa.String(100), nullable=True),
        sa.Column("checksums_json", JSONB, nullable=True),
        sa.Column("blocked_reasons", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -- Observability --
    op.create_table(
        "metric_events",
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("engagement_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("metric_type", sa.String(100), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("actor", UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", JSONB, nullable=True),
    )

    op.create_table(
        "engagements",
        sa.Column("engagement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("current_phase", sa.String(50), nullable=False),
        sa.Column("phase_transitions", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("engagements")
    op.drop_table("metric_events")
    op.drop_table("exports")
    op.drop_table("override_pairs")
    op.drop_table("compilations")
    op.drop_table("mapping_decisions")
    op.drop_table("claims")
    op.drop_table("assumption_links")
    op.drop_table("assumptions")
    op.drop_table("evidence_snippets")
    op.drop_table("line_items")
    op.drop_table("extraction_jobs")
    op.drop_table("documents")
    op.drop_table("scenario_specs")
    op.drop_table("batches")
    op.drop_table("result_sets")
    op.drop_table("run_snapshots")
    op.drop_table("model_data")
    op.drop_table("model_versions")
    op.drop_table("workspaces")
