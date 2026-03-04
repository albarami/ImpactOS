"""Workshop session Pydantic v2 schemas — Sprint 22."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.models.common import ImpactOSBase


class SliderItem(ImpactOSBase):
    """Single sector slider adjustment."""

    sector_code: str = Field(..., min_length=1, max_length=50)
    pct_delta: float = Field(
        ...,
        description="Percent delta applied to baseline shock. E.g. 15.0 means +15%.",
    )


class WorkshopSessionResponse(ImpactOSBase):
    """API response for a single workshop session."""

    session_id: UUID
    workspace_id: UUID
    baseline_run_id: UUID
    slider_config: list[SliderItem]
    status: str  # draft | committed | archived
    committed_run_id: UUID | None = None
    config_hash: str
    preview_summary: dict | None = None
    created_at: datetime
    updated_at: datetime


class WorkshopListResponse(ImpactOSBase):
    """Paginated list of workshop sessions."""

    items: list[WorkshopSessionResponse]
    total: int
    limit: int
    offset: int
