"""B-14 + B-15: Model version list/detail + coefficient retrieval.

Workspace-scoped URLs for consistency. Model versions are global resources.

NOTE: Satellite coefficients are loaded from a reference data file, not stored
per model version. A future sprint will add a coefficient persistence layer
(SatelliteCoefficientRow table) so that coefficients are model-version-specific.
Until then, the same reference coefficients are returned for all model versions
with a ``source: "reference"`` marker and a sector-count mismatch warning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_model_version_repo
from src.db.tables import ModelVersionRow
from src.repositories.engine import ModelVersionRepository

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


def _row_to_response(row: ModelVersionRow) -> ModelVersionResponse:
    return ModelVersionResponse(
        model_version_id=str(row.model_version_id),
        base_year=row.base_year,
        source=row.source,
        sector_count=row.sector_count,
        checksum=row.checksum,
        created_at=row.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Coefficient data (loaded once from synthetic file)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"


def _load_default_coefficients() -> dict[str, Any]:
    path = _DATA_DIR / "saudi_satellites_synthetic_v1.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


_DEFAULT_COEFFICIENTS: dict[str, Any] = _load_default_coefficients()


# ---------------------------------------------------------------------------
# B-14: Model Version List/Detail
# ---------------------------------------------------------------------------


@router.get("/versions", response_model=ModelVersionListResponse)
async def list_model_versions(
    workspace_id: UUID,  # noqa: ARG001
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
    repo: ModelVersionRepository = Depends(get_model_version_repo),
) -> ModelVersionResponse:
    row = await repo.get(model_version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# B-15: Coefficient Retrieval
# ---------------------------------------------------------------------------


@router.get(
    "/versions/{model_version_id}/coefficients",
    response_model=CoefficientsResponse,
)
async def get_coefficients(
    workspace_id: UUID,  # noqa: ARG001
    model_version_id: UUID,
    repo: ModelVersionRepository = Depends(get_model_version_repo),
) -> CoefficientsResponse:
    row = await repo.get(model_version_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Model version not found")

    sector_codes: list[str] = _DEFAULT_COEFFICIENTS.get("sector_codes", [])
    employment: dict[str, Any] = _DEFAULT_COEFFICIENTS.get("employment", {})
    jobs: list[float] = employment.get("jobs_per_sar_million", [])
    imports: list[float] = _DEFAULT_COEFFICIENTS.get("import_ratios", {}).get("values", [])
    va: list[float] = _DEFAULT_COEFFICIENTS.get("va_ratios", {}).get("values", [])

    # Warn if reference data sector count differs from model's actual sector count
    if len(sector_codes) != row.sector_count:
        logger.warning(
            "Coefficient sector count (%d) != model sector count (%d) for %s. "
            "Returning reference data — model-specific coefficients not yet supported.",
            len(sector_codes),
            row.sector_count,
            model_version_id,
        )

    coefficients = [
        SectorCoefficient(
            sector_code=code,
            jobs_coeff=jobs[i] if i < len(jobs) else 0.0,
            import_ratio=imports[i] if i < len(imports) else 0.0,
            va_ratio=va[i] if i < len(va) else 0.0,
        )
        for i, code in enumerate(sector_codes)
    ]

    return CoefficientsResponse(
        model_version_id=str(model_version_id),
        source=_DEFAULT_COEFFICIENTS.get("source", "reference"),
        sector_coefficients=coefficients,
    )
