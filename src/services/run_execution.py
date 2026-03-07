"""RunExecutionService — shared deterministic engine execution (Sprint 28).

Single source of truth for engine runs. Both the chat handler and the
API route call this service. No internal HTTP self-calls.

Agent-to-Math Boundary: this service calls BatchRunner.run() for
deterministic computation — it never performs economic calculations itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.data.workforce.satellite_coeff_loader import load_satellite_coefficients
from src.engine.batch import BatchRequest, BatchRunner, ScenarioInput, SingleRunResult
from src.engine.feasibility import constraints_to_specs
from src.engine.model_store import LoadedModel, ModelStore, compute_model_checksum
from src.engine.satellites import SatelliteCoefficients
from src.models.common import new_uuid7
from src.models.feasibility import Constraint
from src.models.model_version import ModelVersion
from src.repositories.engine import (
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.feasibility import ConstraintSetRepository
from src.repositories.governance import ClaimRepository
from src.repositories.scenarios import ScenarioVersionRepository
from src.repositories.workforce import WorkforceResultRepository

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Normalized dataclasses
# ------------------------------------------------------------------


@dataclass(frozen=True)
class RunFromScenarioInput:
    """Chat path: resolve scenario into engine inputs."""

    workspace_id: UUID
    scenario_spec_id: UUID
    scenario_spec_version: int | None = None  # None = latest


@dataclass(frozen=True)
class RunFromRequestInput:
    """API path: pre-parsed engine inputs."""

    workspace_id: UUID
    model_version_id: UUID
    annual_shocks: dict  # dict[int, np.ndarray]
    base_year: int
    satellite_coefficients: object  # SatelliteCoefficients
    deflators: dict | None = None
    baseline_run_id: UUID | None = None
    scenario_spec_id: UUID | None = None
    scenario_spec_version: int | None = None


@dataclass(frozen=True)
class RunExecutionResult:
    """Result of an engine run execution."""

    status: Literal["COMPLETED", "FAILED"]
    run_id: UUID | None = None
    model_version_id: UUID | None = None
    scenario_spec_id: UUID | None = None
    scenario_spec_version: int | None = None
    result_summary: dict | None = None
    error: str | None = None


@dataclass
class RunRepositories:
    """All repos needed for a run execution."""

    scenario_repo: ScenarioVersionRepository
    mv_repo: ModelVersionRepository
    md_repo: ModelDataRepository
    snap_repo: RunSnapshotRepository
    rs_repo: ResultSetRepository
    claim_repo: ClaimRepository | None = None  # P4-1: optional for backward compat
    constraint_repo: ConstraintSetRepository | None = None
    workforce_result_repo: WorkforceResultRepository | None = None


# ------------------------------------------------------------------
# Module-level singletons (same pattern as src/api/runs.py)
# ------------------------------------------------------------------

# Reuse a global model store (in-memory LRU cache for synchronous engine access)
_model_store = ModelStore()

# Per-model locks to prevent thundering herd on DB fallback
_model_locks: dict[UUID, asyncio.Lock] = {}
_global_lock = asyncio.Lock()

ALLOWED_RUNTIME_PROVENANCE = frozenset({"curated_real"})


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------


class RunExecutionService:
    """Shared deterministic engine execution service.

    Both ChatToolExecutor._handle_run_engine() and the API route
    POST /v1/workspaces/{ws}/engine/runs call this service.
    """

    async def execute_from_scenario(
        self,
        input: RunFromScenarioInput,
        repos: RunRepositories,
    ) -> RunExecutionResult:
        """Execute engine run from a scenario_spec_id (chat path).

        Resolves scenario -> model -> satellite coefficients -> BatchRunner.run().
        Persists RunSnapshot + ResultSet rows.
        Returns result_summary derived from persisted rows.
        """
        # 1. Resolve scenario (version pinning or latest)
        if input.scenario_spec_version is not None:
            row = await repos.scenario_repo.get_by_id_and_version(
                input.scenario_spec_id, input.scenario_spec_version,
            )
            if row is None:
                return RunExecutionResult(
                    status="FAILED",
                    error=(
                        f"Scenario {input.scenario_spec_id} "
                        f"v{input.scenario_spec_version} not found in workspace"
                    ),
                )
            # Workspace check inside the service (design doc 3.1)
            if row.workspace_id != input.workspace_id:
                return RunExecutionResult(
                    status="FAILED",
                    error=(
                        f"Scenario {input.scenario_spec_id} "
                        f"v{input.scenario_spec_version} not found in workspace"
                    ),
                )
        else:
            row = await repos.scenario_repo.get_latest_by_workspace(
                input.scenario_spec_id, input.workspace_id,
            )
            if row is None:
                return RunExecutionResult(
                    status="FAILED",
                    error=f"Scenario {input.scenario_spec_id} not found in workspace",
                )

        model_version_id = row.base_model_version_id

        # 2. Enforce model provenance (D-5.1: only curated_real permitted)
        mv_row = await repos.mv_repo.get(model_version_id)
        if mv_row is None:
            return RunExecutionResult(
                status="FAILED",
                error=f"Model {model_version_id} not found",
            )
        prov = getattr(mv_row, "provenance_class", "unknown")
        if prov not in ALLOWED_RUNTIME_PROVENANCE:
            return RunExecutionResult(
                status="FAILED",
                error=(
                    f"Model provenance_class '{prov}' not allowed "
                    f"for runtime execution"
                ),
            )

        # 3. Load model into cache (two-phase: cache check, then DB fallback)
        try:
            loaded = await self._ensure_model_loaded(
                model_version_id, repos.mv_repo, repos.md_repo,
            )
        except Exception as exc:
            return RunExecutionResult(
                status="FAILED",
                error=f"Failed to load model: {str(exc)[:200]}",
            )

        # 4. Resolve satellite coefficients from curated loader
        try:
            loaded_coeffs = load_satellite_coefficients(
                year=row.base_year,
                sector_codes=loaded.sector_codes,
            )
            coeffs = loaded_coeffs.coefficients
        except Exception as exc:
            return RunExecutionResult(
                status="FAILED",
                error=f"Failed to load satellite coefficients: {str(exc)[:200]}",
            )

        # 4b. Resolve workspace feasibility constraints for this model.
        constraint_rows = []
        if repos.constraint_repo is not None:
            constraint_rows = await repos.constraint_repo.get_by_workspace(input.workspace_id)
        constraint_set_row = next(
            (r for r in constraint_rows if r.model_version_id == model_version_id),
            None,
        )
        constraint_specs = []
        if constraint_set_row is not None:
            constraint_models = [
                Constraint.model_validate(c) for c in (constraint_set_row.constraints or [])
            ]
            constraint_specs = constraints_to_specs(constraint_models, loaded.sector_codes)

        # 5. Build scenario input from ScenarioSpec
        shocks = row.shock_items or []
        annual_shocks = self._build_annual_shocks(
            shocks, row.base_year, loaded.sector_codes,
        )

        scenario = ScenarioInput(
            scenario_spec_id=row.scenario_spec_id,
            scenario_spec_version=row.version,
            name=row.name,
            annual_shocks=annual_shocks,
            base_year=row.base_year,
        )

        # 6. Execute deterministic engine (Agent-to-Math Boundary preserved)
        version_refs = self._make_version_refs()
        settings = get_settings()
        runner = BatchRunner(
            model_store=_model_store,
            environment=settings.ENVIRONMENT.value,
        )
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=model_version_id,
            satellite_coefficients=coeffs,
            version_refs=version_refs,
            constraints=constraint_specs,
        )

        try:
            batch_result = runner.run(request)
        except Exception as exc:
            return RunExecutionResult(
                status="FAILED",
                error=f"Engine execution failed: {str(exc)[:200]}",
            )

        sr = batch_result.run_results[0]

        # 7. Persist snapshot + result sets
        await self._persist_run_result(
            sr,
            repos.snap_repo,
            repos.rs_repo,
            workspace_id=input.workspace_id,
            scenario_spec_id=row.scenario_spec_id,
            scenario_spec_version=row.version,
            model_denomination=getattr(loaded.model_version, "model_denomination", "UNKNOWN"),
            constraint_set_version_id=(
                constraint_set_row.constraint_set_id if constraint_set_row is not None else None
            ),
        )

        # 8. Build result_summary from persisted rows (NOT from in-memory BatchResult)
        rs_rows = await repos.rs_repo.get_by_run(sr.snapshot.run_id)
        result_summary: dict[str, dict] = {}
        for rs_row in rs_rows:
            if getattr(rs_row, "series_kind", None) is None:
                result_summary[rs_row.metric_type] = rs_row.values

        # 9. P4-1: Auto-create claims from results (NFF governance)
        if repos.claim_repo is not None and result_summary:
            from src.governance.claim_extractor import create_claims_from_results

            claims = create_claims_from_results(
                result_summary, run_id=sr.snapshot.run_id,
            )
            for claim in claims:
                await repos.claim_repo.create(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    claim_type=claim.claim_type.value,
                    status=claim.status.value,
                    run_id=sr.snapshot.run_id,
                )
            _logger.info(
                "P4-1: Auto-created %d claims from run %s",
                len(claims), sr.snapshot.run_id,
            )

        if repos.workforce_result_repo is not None:
            await self._persist_workforce_result(
                sr=sr,
                repo=repos.workforce_result_repo,
                workspace_id=input.workspace_id,
                coefficients=coeffs,
                employment_coeff_year=getattr(
                    loaded_coeffs.provenance, "employment_coeff_year", row.base_year,
                ),
            )

        return RunExecutionResult(
            status="COMPLETED",
            run_id=sr.snapshot.run_id,
            model_version_id=model_version_id,
            scenario_spec_id=row.scenario_spec_id,
            scenario_spec_version=row.version,
            result_summary=result_summary,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_annual_shocks(
        self,
        shock_items: list,
        base_year: int,
        sector_codes: list[str],
    ) -> dict[int, np.ndarray]:
        """Convert shock_items list into annual_shocks dict for BatchRunner.

        Parses FINAL_DEMAND_SHOCK items into per-year numpy delta vectors
        aligned to the model's sector order. Other shock types (IMPORT_SUBSTITUTION,
        LOCAL_CONTENT, CONSTRAINT_OVERRIDE) are ignored for the base I-O run.

        Empty shocks = zero delta at base_year (identity run).

        Same logic as src/api/scenarios.py::_shock_items_to_annual_shocks().
        """
        sector_index = {code: i for i, code in enumerate(sector_codes)}
        n = len(sector_codes)
        year_shocks: dict[int, np.ndarray] = {}

        for item in shock_items:
            if item.get("type") != "FINAL_DEMAND_SHOCK":
                continue
            year = item.get("year", base_year)
            code = item.get("sector_code")
            amount = item.get("amount_real_base_year", 0.0)
            domestic_share = item.get("domestic_share", 1.0)

            if code not in sector_index:
                _logger.warning(
                    "Shock sector_code %r not in model sector_codes, skipping",
                    code,
                )
                continue

            if year not in year_shocks:
                year_shocks[year] = np.zeros(n, dtype=np.float64)

            year_shocks[year][sector_index[code]] += amount * domestic_share

        # Guarantee at least one year entry (identity run if no shocks)
        if not year_shocks:
            year_shocks[base_year] = np.zeros(n, dtype=np.float64)

        return year_shocks

    def _make_version_refs(self) -> dict[str, UUID]:
        """Generate placeholder version refs for engine run."""
        return {
            "taxonomy_version_id": new_uuid7(),
            "concordance_version_id": new_uuid7(),
            "mapping_library_version_id": new_uuid7(),
            "assumption_library_version_id": new_uuid7(),
            "prompt_pack_version_id": new_uuid7(),
        }

    async def _ensure_model_loaded(
        self,
        model_version_id: UUID,
        mv_repo: ModelVersionRepository,
        md_repo: ModelDataRepository,
    ) -> LoadedModel:
        """Load model from cache, falling back to DB on miss.

        Same logic as src/api/runs.py::_ensure_model_loaded() but extracted
        into the shared service. Uses double-checked locking for concurrency.
        """
        # Fast path: cache hit (no lock needed)
        try:
            return _model_store.get(model_version_id)
        except KeyError:
            pass

        # Cache miss — acquire per-model lock to prevent thundering herd
        async with _global_lock:
            if model_version_id not in _model_locks:
                _model_locks[model_version_id] = asyncio.Lock()
            lock = _model_locks[model_version_id]

        async with lock:
            # Double-check after acquiring lock
            try:
                return _model_store.get(model_version_id)
            except KeyError:
                pass

            # Load from DB
            _logger.info(
                "Cache miss for model %s — loading from DB", model_version_id,
            )
            mv_row = await mv_repo.get(model_version_id)
            if mv_row is None:
                raise ValueError(f"Model {model_version_id} not found")
            md_row = await md_repo.get(model_version_id)
            if md_row is None:
                raise ValueError(
                    f"Model data for {model_version_id} not found",
                )

            # Reconstruct arrays
            z_matrix = np.array(md_row.z_matrix_json, dtype=np.float64)
            x_vector = np.array(md_row.x_vector_json, dtype=np.float64)

            # Rehydrate extended artifacts so LoadedModel has Type II prerequisites
            artifact_kwargs: dict[str, object] = {}
            for key in (
                "compensation_of_employees",
                "gross_operating_surplus",
                "taxes_less_subsidies",
                "household_consumption_shares",
                "imports_vector",
                "deflator_series",
            ):
                val = getattr(md_row, f"{key}_json", None)
                if val is not None:
                    artifact_kwargs[key] = val
            fd_val = getattr(md_row, "final_demand_f_json", None)
            if fd_val is not None:
                artifact_kwargs["final_demand_F"] = fd_val

            mv = ModelVersion(
                model_version_id=mv_row.model_version_id,
                base_year=mv_row.base_year,
                source=mv_row.source,
                sector_count=mv_row.sector_count,
                checksum=mv_row.checksum,
                model_denomination=getattr(mv_row, "model_denomination", "UNKNOWN"),
                **artifact_kwargs,
            )
            loaded = LoadedModel(
                model_version=mv,
                Z=z_matrix,
                x=x_vector,
                sector_codes=list(md_row.sector_codes),
            )
            _model_store.cache_prevalidated(loaded)
            _logger.info(
                "Rehydrated model %s from DB into cache", model_version_id,
            )
            return loaded

    async def _persist_run_result(
        self,
        sr: SingleRunResult,
        snap_repo: RunSnapshotRepository,
        rs_repo: ResultSetRepository,
        workspace_id: UUID | None = None,
        scenario_spec_id: UUID | None = None,
        scenario_spec_version: int | None = None,
        model_denomination: str = "UNKNOWN",
        constraint_set_version_id: UUID | None = None,
    ) -> None:
        """Persist a SingleRunResult to DB (snapshot + result sets).

        Same logic as src/api/runs.py::_persist_run_result().
        """
        snap = sr.snapshot
        await snap_repo.create(
            run_id=snap.run_id,
            model_version_id=snap.model_version_id,
            taxonomy_version_id=snap.taxonomy_version_id,
            concordance_version_id=snap.concordance_version_id,
            mapping_library_version_id=snap.mapping_library_version_id,
            assumption_library_version_id=snap.assumption_library_version_id,
            prompt_pack_version_id=snap.prompt_pack_version_id,
            constraint_set_version_id=constraint_set_version_id,
            workspace_id=workspace_id,
            scenario_spec_id=scenario_spec_id,
            scenario_spec_version=scenario_spec_version,
            model_denomination=model_denomination,
        )
        for rs in sr.result_sets:
            await rs_repo.create(
                result_id=rs.result_id,
                run_id=rs.run_id,
                metric_type=rs.metric_type,
                values=rs.values,
                sector_breakdowns=rs.sector_breakdowns,
                workspace_id=workspace_id,
                year=rs.year,
                series_kind=rs.series_kind,
                baseline_run_id=rs.baseline_run_id,
            )

    async def _persist_workforce_result(
        self,
        *,
        sr: SingleRunResult,
        repo: WorkforceResultRepository,
        workspace_id: UUID,
        coefficients: SatelliteCoefficients,
        employment_coeff_year: int,
    ) -> None:
        """Persist workforce/saudization outputs derived from the real run result sets."""
        result_map = {
            rs.metric_type: rs.values
            for rs in sr.result_sets
            if getattr(rs, "series_kind", None) is None
        }
        employment = result_map.get("employment")
        if not employment:
            return

        ready = result_map.get("saudization_saudi_ready", {})
        trainable = result_map.get("saudization_saudi_trainable", {})
        expat = result_map.get("saudization_expat_reliant", {})

        sectors = sorted(set(employment) | set(ready) | set(trainable) | set(expat))
        per_sector = []
        for sector in sectors:
            total_jobs = float(employment.get(sector, 0.0))
            per_sector.append({
                "sector_code": sector,
                "total_jobs": total_jobs,
                "saudi_ready_jobs": float(ready.get(sector, 0.0)),
                "saudi_trainable_jobs": float(trainable.get(sector, 0.0)),
                "expat_reliant_jobs": float(expat.get(sector, 0.0)),
            })

        payload = {
            "per_sector": per_sector,
            "totals": {
                "total_jobs": sum(float(v) for v in employment.values()),
                "total_saudi_ready": sum(float(v) for v in ready.values()),
                "total_saudi_trainable": sum(float(v) for v in trainable.values()),
                "total_expat_reliant": sum(float(v) for v in expat.values()),
            },
            "has_saudization_split": bool(ready or trainable or expat),
        }
        coeff_hash = hashlib.sha256(
            json.dumps(
                {
                    "jobs_coeff": coefficients.jobs_coeff.tolist(),
                    "import_ratio": coefficients.import_ratio.tolist(),
                    "va_ratio": coefficients.va_ratio.tolist(),
                    "version_id": str(coefficients.version_id),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        existing = await repo.get_existing(
            run_id=sr.snapshot.run_id,
            employment_coefficients_id=coefficients.version_id,
            employment_coefficients_version=1,
            delta_x_source="RESULT_SET",
        )
        if existing is not None:
            return

        await repo.create(
            workforce_result_id=new_uuid7(),
            workspace_id=workspace_id,
            run_id=sr.snapshot.run_id,
            employment_coefficients_id=coefficients.version_id,
            employment_coefficients_version=1,
            results=payload,
            confidence_summary={
                "employment_coeff_year": employment_coeff_year,
                "has_saudization_split": payload["has_saudization_split"],
            },
            data_quality_notes=[
                f"Employment coefficients year: {employment_coeff_year}",
                "Saudization split derived from persisted run result sets.",
            ],
            satellite_coefficients_hash=f"sha256:{coeff_hash}",
            delta_x_source="RESULT_SET",
        )
