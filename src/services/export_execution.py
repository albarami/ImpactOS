"""ExportExecutionService -- shared export orchestration (Sprint 28).

Single source of truth for export execution. Both the chat handler and
the API route call this service. No internal HTTP self-calls.

Deterministic -- no LLM calls. Delegates to ExportOrchestrator for
format generation, watermarking, and checksum computation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from src.api.runs import ALLOWED_RUNTIME_PROVENANCE
from src.export.artifact_storage import ExportArtifactStorage
from src.export.orchestrator import ExportOrchestrator, ExportRequest, ExportStatus
from src.models.common import (
    ClaimStatus,
    ClaimType,
    DisclosureTier,
    ExportMode,
)
from src.models.governance import Assumption, AssumptionRange, Claim
from src.quality.models import RunQualityAssessment
from src.repositories.data_quality import DataQualityRepository
from src.repositories.engine import ModelVersionRepository, RunSnapshotRepository
from src.repositories.exports import ExportRepository
from src.repositories.governance import AssumptionRepository, ClaimRepository
from src.repositories.scenarios import ScenarioVersionRepository

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Normalized dataclasses
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ExportExecutionInput:
    """Input for export execution (both chat and API paths)."""

    workspace_id: UUID
    run_id: UUID
    mode: ExportMode
    export_formats: list[str]
    pack_data: dict


@dataclass(frozen=True)
class ExportExecutionResult:
    """Result of an export execution."""

    status: Literal["COMPLETED", "BLOCKED", "FAILED"]
    export_id: UUID | None = None
    checksums: dict[str, str] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    artifact_refs: dict[str, str] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ExportRepositories:
    """All repos needed for an export execution."""

    export_repo: ExportRepository
    claim_repo: ClaimRepository
    quality_repo: DataQualityRepository
    snap_repo: RunSnapshotRepository
    mv_repo: ModelVersionRepository
    artifact_store: ExportArtifactStorage
    assumption_repo: AssumptionRepository | None = None  # P4-3: optional for backward compat
    scenario_repo: ScenarioVersionRepository | None = None


# ------------------------------------------------------------------
# Helpers (reused from src/api/exports.py)
# ------------------------------------------------------------------


def _assumption_row_to_model(row) -> Assumption:
    """Convert AssumptionRow to Assumption Pydantic model for gate checks."""
    from src.models.common import AssumptionStatus, AssumptionType

    range_obj = None
    if row.range_json and isinstance(row.range_json, dict):
        range_obj = AssumptionRange(
            min=row.range_json.get("min", 0),
            max=row.range_json.get("max", 0),
        )

    return Assumption(
        assumption_id=row.assumption_id,
        type=AssumptionType(row.type),
        value=row.value,
        range=range_obj,
        units=row.units,
        justification=row.justification,
        evidence_refs=row.evidence_refs or [],
        status=AssumptionStatus(row.status),
        approved_by=getattr(row, "approved_by", None),
        approved_at=getattr(row, "approved_at", None),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _claim_row_to_model(row) -> Claim:
    """Convert ClaimRow to Claim Pydantic model for NFF gate checks."""
    return Claim(
        claim_id=row.claim_id,
        text=row.text,
        claim_type=ClaimType(row.claim_type),
        status=ClaimStatus(row.status),
        disclosure_tier=DisclosureTier(row.disclosure_tier),
        model_refs=[],
        evidence_refs=[],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _check_model_provenance(
    run_id: UUID,
    snap_repo: RunSnapshotRepository,
    mv_repo: ModelVersionRepository,
) -> bool:
    """Check if the run's model has disallowed provenance.

    Returns True if provenance_class is NOT in ALLOWED_RUNTIME_PROVENANCE.
    """
    snap_row = await snap_repo.get(run_id)
    if snap_row is None:
        return True
    mv_row = await mv_repo.get(snap_row.model_version_id)
    if mv_row is None:
        return True
    prov = getattr(mv_row, "provenance_class", "unknown")
    return prov not in ALLOWED_RUNTIME_PROVENANCE


# ------------------------------------------------------------------
# Stateless orchestrator singleton
# ------------------------------------------------------------------

_orchestrator = ExportOrchestrator()


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------


class ExportExecutionService:
    """Shared export orchestration service.

    Both ChatToolExecutor._handle_create_export() and the API route
    POST /v1/workspaces/{ws}/exports call this service.
    """

    async def execute(
        self,
        input: ExportExecutionInput,
        repos: ExportRepositories,
    ) -> ExportExecutionResult:
        """Execute export pipeline with governance checks.

        1. Validate run exists and belongs to workspace.
        2. Load claims, quality assessment, model provenance.
        3. Call ExportOrchestrator.execute().
        4. Store artifacts via ExportArtifactStorage when COMPLETED.
        5. Persist export record via ExportRepository.create().
        6. Return truthful status: COMPLETED, BLOCKED, or FAILED.
        """
        # 1. Validate run exists and belongs to the workspace
        snap_row = await repos.snap_repo.get(input.run_id)
        if snap_row is None:
            return ExportExecutionResult(
                status="FAILED",
                error=f"Run {input.run_id} not found",
            )

        if snap_row.workspace_id != input.workspace_id:
            return ExportExecutionResult(
                status="FAILED",
                error=(
                    f"Run {input.run_id} does not belong to "
                    f"workspace {input.workspace_id}"
                ),
            )

        # 2. Load governance inputs (same as src/api/exports.py create_export)
        claim_rows = await repos.claim_repo.get_by_run(input.run_id)
        claims = [_claim_row_to_model(r) for r in claim_rows]

        # Scope assumptions to the exported scenario only.
        assumptions: list[Assumption] | None = None
        if repos.assumption_repo is not None:
            try:
                assumption_rows: list = []
                scenario_spec_id = getattr(snap_row, "scenario_spec_id", None)
                if scenario_spec_id is not None:
                    scenario_row = None
                    if repos.scenario_repo is not None:
                        scenario_row = await repos.scenario_repo.get_by_id_and_version(
                            scenario_spec_id,
                            getattr(snap_row, "scenario_spec_version", 1) or 1,
                        )
                    if scenario_row is not None and getattr(scenario_row, "assumption_ids", None):
                        assumption_ids = [
                            UUID(str(assumption_id))
                            for assumption_id in scenario_row.assumption_ids
                        ]
                        assumption_rows = await repos.assumption_repo.list_by_ids(
                            assumption_ids
                        )
                    else:
                        assumption_rows = await repos.assumption_repo.list_linked_to(
                            scenario_spec_id, link_type="scenario",
                        )
                    _logger.info(
                        "Loaded %d assumptions scoped to scenario %s",
                        len(assumption_rows), scenario_spec_id,
                    )
                if assumption_rows:
                    assumptions = [
                        _assumption_row_to_model(r) for r in assumption_rows
                    ]
            except Exception:
                _logger.warning(
                    "Failed to load assumptions for run %s",
                    input.run_id,
                    exc_info=True,
                )

        quality_assessment: RunQualityAssessment | None = None
        quality_row = await repos.quality_repo.get_by_run(input.run_id)
        if quality_row is not None and quality_row.payload:
            try:
                quality_assessment = RunQualityAssessment.model_validate(
                    quality_row.payload,
                )
            except Exception:
                pass

        model_provenance_disallowed = await _check_model_provenance(
            input.run_id, repos.snap_repo, repos.mv_repo,
        )

        # 3. Build ExportRequest and call orchestrator
        request = ExportRequest(
            run_id=input.run_id,
            workspace_id=input.workspace_id,
            mode=input.mode,
            export_formats=input.export_formats,
            pack_data=input.pack_data,
        )

        try:
            record = _orchestrator.execute(
                request=request,
                claims=claims,
                assumptions=assumptions,  # P4-3: pass assumptions to gate
                quality_assessment=quality_assessment,
                model_provenance_disallowed=model_provenance_disallowed,
            )
        except Exception as exc:
            return ExportExecutionResult(
                status="FAILED",
                error=f"Export orchestration failed: {str(exc)[:200]}",
            )

        # 4. Store artifacts and persist DB record
        # Wrap in try/except so failures in artifact storage or DB
        # persistence are returned as FAILED (not bubbled to generic
        # handler_exception), honoring the COMPLETED/BLOCKED/FAILED contract.
        try:
            artifact_refs: dict[str, str] = {}
            if record.artifacts:
                for fmt, data in record.artifacts.items():
                    key = ExportArtifactStorage.build_key(
                        str(record.export_id), fmt,
                    )
                    repos.artifact_store.store(key, data)
                    artifact_refs[fmt] = key

            # 5. Persist export record in DB
            await repos.export_repo.create(
                export_id=record.export_id,
                run_id=record.run_id,
                mode=record.mode.value,
                status=record.status.value,
                checksums_json=record.checksums,
                blocked_reasons=record.blocking_reasons,
                artifact_refs_json=artifact_refs or None,
            )
        except Exception as exc:
            _logger.exception(
                "Failed to store artifacts or persist export record for %s",
                record.export_id,
            )
            return ExportExecutionResult(
                status="FAILED",
                export_id=record.export_id,
                error=f"Post-orchestration persistence failed: {str(exc)[:200]}",
            )

        # 6. Map orchestrator result to service result
        if record.status == ExportStatus.COMPLETED:
            return ExportExecutionResult(
                status="COMPLETED",
                export_id=record.export_id,
                checksums=record.checksums,
                artifact_refs=artifact_refs,
            )
        elif record.status == ExportStatus.BLOCKED:
            return ExportExecutionResult(
                status="BLOCKED",
                export_id=record.export_id,
                blocking_reasons=record.blocking_reasons,
            )
        else:
            # ExportStatus.FAILED (if orchestrator ever returns it)
            return ExportExecutionResult(
                status="FAILED",
                export_id=record.export_id,
                error="Export failed during orchestration",
            )
