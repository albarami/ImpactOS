"""B-14 + B-15: Model version list/detail + coefficient retrieval.

Workspace-scoped URLs for consistency. Model versions are global resources.

B-15 coefficients are model-linked:
- sector_codes, VA ratios, import ratios derived from persisted ModelDataRow (Z, x)
- employment coefficients from EmploymentCoefficientsRow when registered
- fallback to zero jobs_coeff when no employment coefficients exist for the model
"""

from __future__ import annotations

import logging
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth_deps import WorkspaceMember, require_workspace_member
from src.api.dependencies import (
    get_employment_coefficients_repo,
    get_model_data_repo,
    get_model_version_repo,
)
from src.db.tables import ModelDataRow, ModelVersionRow
from src.repositories.engine import ModelDataRepository, ModelVersionRepository
from src.repositories.workforce import EmploymentCoefficientsRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/workspaces/{workspace_id}/models",
    tags=["models"],
)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ModelVersionResponse(BaseModel):
    model_version_id: str
    base_year: int
    source: str
    sector_count: int
    checksum: str
    created_at: str
    status: str = "AVAILABLE"
    final_demand_f: list[list[float]] | None = Field(
        default=None,
        alias="final_demand_F",
    )
    imports_vector: list[float] | None = None
    compensation_of_employees: list[float] | None = None
    gross_operating_surplus: list[float] | None = None
    taxes_less_subsidies: list[float] | None = None
    household_consumption_shares: list[float] | None = None
    deflator_series: dict[str, float] | None = None
    sg_provenance: dict | None = None


class ModelVersionListResponse(BaseModel):
    items: list[ModelVersionResponse]
    total: int


class SectorCoefficient(BaseModel):
    sector_code: str
    jobs_coeff: float
    import_ratio: float
    va_ratio: float


class CoefficientsResponse(BaseModel):
    model_version_id: str
    source: str
    sector_coefficients: list[SectorCoefficient]


def _row_to_response(
    row: ModelVersionRow,
    model_data: ModelDataRow | None = None,
) -> ModelVersionResponse:
    deflator_series = None
    if model_data is not None and model_data.deflator_series_json is not None:
        deflator_series = {
            str(k): float(v) for k, v in model_data.deflator_series_json.items()
        }

    return ModelVersionResponse(
        model_version_id=str(row.model_version_id),
        base_year=row.base_year,
        source=row.source,
        sector_count=row.sector_count,
        checksum=row.checksum,
        created_at=row.created_at.isoformat(),
        final_demand_f=(
            model_data.final_demand_f_json
            if model_data is not None else None
        ),
        imports_vector=(
            model_data.imports_vector_json
            if model_data is not None else None
        ),
        compensation_of_employees=(
            model_data.compensation_of_employees_json
            if model_data is not None else None
        ),
        gross_operating_surplus=(
            model_data.gross_operating_surplus_json
            if model_data is not None else None
        ),
        taxes_less_subsidies=(
            model_data.taxes_less_subsidies_json
            if model_data is not None else None
        ),
        household_consumption_shares=(
            model_data.household_consumption_shares_json
            if model_data is not None else None
        ),
        deflator_series=deflator_series,
        sg_provenance=getattr(row, "sg_provenance", None),
    )


# ---------------------------------------------------------------------------
# B-14: Model Version List/Detail
# ---------------------------------------------------------------------------


@router.get("/versions", response_model=ModelVersionListResponse)
async def list_model_versions(
    workspace_id: UUID,  # noqa: ARG001
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: ModelVersionRepository = Depends(get_model_version_repo),
) -> ModelVersionListResponse:
    rows = await repo.list_all()
    return ModelVersionListResponse(
        items=[_row_to_response(r) for r in rows],
        total=len(rows),
    )


@router.get("/versions/{model_version_id}", response_model=ModelVersionResponse)
async def get_model_version(
    workspace_id: UUID,  # noqa: ARG001
    model_version_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
) -> ModelVersionResponse:
    row = await repo.get(model_version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    model_data = await md_repo.get(model_version_id)
    return _row_to_response(row, model_data)


# ---------------------------------------------------------------------------
# B-15: Coefficient Retrieval (model-linked)
# ---------------------------------------------------------------------------


def _compute_va_ratios(z_matrix: list[list[float]], x_vector: list[float]) -> np.ndarray:
    """Compute value-added ratios from IO model: va_i = 1 - sum(A_col_i).

    Same formula as satellite_coeff_loader._load_io_ratios().
    """
    z = np.array(z_matrix, dtype=np.float64)
    x = np.array(x_vector, dtype=np.float64)
    x_safe = np.where(x > 0, x, 1.0)
    a_mat = z / x_safe[np.newaxis, :]
    va = 1.0 - a_mat.sum(axis=0)
    return np.clip(va, 0.0, 1.0)


def _default_import_ratios(n: int) -> np.ndarray:
    """Default import ratios when curated data unavailable.

    Matches satellite_coeff_loader.py default (0.15 per sector).
    """
    return np.full(n, 0.15, dtype=np.float64)


@router.get(
    "/versions/{model_version_id}/coefficients",
    response_model=CoefficientsResponse,
)
async def get_coefficients(
    workspace_id: UUID,  # noqa: ARG001
    model_version_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    mv_repo: ModelVersionRepository = Depends(get_model_version_repo),
    md_repo: ModelDataRepository = Depends(get_model_data_repo),
    ec_repo: EmploymentCoefficientsRepository = Depends(get_employment_coefficients_repo),
) -> CoefficientsResponse:
    # 1. Verify model version exists
    mv_row = await mv_repo.get(model_version_id)
    if mv_row is None:
        raise HTTPException(status_code=404, detail="Model version not found")

    # 2. Load persisted model data (Z, x, sector_codes)
    model_data = await md_repo.get(model_version_id)
    if model_data is None:
        raise HTTPException(
            status_code=404,
            detail="Model data not found for this version",
        )

    sector_codes: list[str] = model_data.sector_codes
    n = len(sector_codes)

    # 3. Compute VA ratios from persisted IO model
    va_ratios = _compute_va_ratios(model_data.z_matrix_json, model_data.x_vector_json)
    import_ratios = _default_import_ratios(n)

    # 4. Load employment coefficients linked to this model version (if any)
    ec_rows = await ec_repo.get_by_model_version(model_version_id)
    jobs_by_sector: dict[str, float] = {}
    source = "model-data"

    if ec_rows:
        # Use the latest version's coefficients
        latest = ec_rows[0]  # already ordered by created_at desc
        for coeff in latest.coefficients:
            code = coeff.get("sector_code", "")
            jobs = coeff.get("jobs_per_million_sar", 0.0)
            jobs_by_sector[code] = jobs
        source = "model-data+employment"
        logger.info(
            "Loaded %d employment coefficients for model %s (ec_id=%s, v%d)",
            len(jobs_by_sector),
            model_version_id,
            latest.employment_coefficients_id,
            latest.version,
        )
    else:
        logger.info(
            "No employment coefficients registered for model %s; "
            "jobs_coeff will be 0.0 for all sectors.",
            model_version_id,
        )

    # 5. Build aligned response
    coefficients = [
        SectorCoefficient(
            sector_code=code,
            jobs_coeff=jobs_by_sector.get(code, 0.0),
            import_ratio=float(import_ratios[i]),
            va_ratio=float(va_ratios[i]),
        )
        for i, code in enumerate(sector_codes)
    ]

    return CoefficientsResponse(
        model_version_id=str(model_version_id),
        source=source,
        sector_coefficients=coefficients,
    )
