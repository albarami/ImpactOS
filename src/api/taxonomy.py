"""B-6: Taxonomy browsing API.

Loads ISIC Rev.4 taxonomy from curated JSON files (read-only reference data).
Workspace-scoped URL for consistency; taxonomy data is global.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(
    prefix="/v1/workspaces/{workspace_id}/taxonomy",
    tags=["taxonomy"],
)

# ---------------------------------------------------------------------------
# Load taxonomy data at module level (read-only, never changes at runtime)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "curated"


def _load_taxonomy() -> list[dict[str, str | None]]:
    """Load sections and divisions from curated JSON files."""
    items: list[dict[str, str | None]] = []

    sections_path = _DATA_DIR / "sector_taxonomy_isic4.json"
    if sections_path.exists():
        with open(sections_path, encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("sectors", []):
            if not s.get("is_active", True):
                continue
            items.append({
                "sector_code": s["sector_code"],
                "name_en": s["sector_name_en"],
                "name_ar": s.get("sector_name_ar"),
                "parent_code": s.get("parent_sector_code"),
                "level": s.get("level", "section"),
                "description": s.get("description", ""),
            })

    divisions_path = _DATA_DIR / "sector_taxonomy_isic4_divisions.json"
    if divisions_path.exists():
        with open(divisions_path, encoding="utf-8") as f:
            data = json.load(f)
        for d in data.get("sectors", []):
            if not d.get("is_active", True):
                continue
            items.append({
                "sector_code": d["division_code"],
                "name_en": d["sector_name_en"],
                "name_ar": d.get("sector_name_ar"),
                "parent_code": d.get("parent_section"),
                "level": "division",
                "description": d.get("description", ""),
            })

    return items


_TAXONOMY: list[dict[str, str | None]] = _load_taxonomy()
_TAXONOMY_BY_CODE: dict[str, dict[str, str | None]] = {
    t["sector_code"]: t for t in _TAXONOMY  # type: ignore[misc]
}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SectorItem(BaseModel):
    sector_code: str
    name_en: str
    name_ar: str | None = None
    parent_code: str | None = None
    level: str
    description: str = ""


class SectorListResponse(BaseModel):
    items: list[SectorItem]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/sectors", response_model=SectorListResponse)
async def list_sectors(
    workspace_id: UUID,
    level: str | None = Query(default=None, description="Filter by level: section or division"),
) -> SectorListResponse:
    """List all taxonomy sectors, optionally filtered by level."""
    items = _TAXONOMY
    if level:
        items = [t for t in items if t["level"] == level]
    return SectorListResponse(
        items=[SectorItem(**t) for t in items],  # type: ignore[arg-type]
        total=len(items),
    )


@router.get("/sectors/search", response_model=SectorListResponse)
async def search_sectors(
    workspace_id: UUID,
    q: str = Query(min_length=1, description="Search query"),
) -> SectorListResponse:
    """Search sectors by code or English name (case-insensitive)."""
    q_lower = q.lower()
    matches = [
        t for t in _TAXONOMY
        if q_lower in (t.get("sector_code") or "").lower()
        or q_lower in (t.get("name_en") or "").lower()
    ]
    return SectorListResponse(
        items=[SectorItem(**m) for m in matches],  # type: ignore[arg-type]
        total=len(matches),
    )


@router.get("/sectors/{sector_code}", response_model=SectorItem)
async def get_sector(
    workspace_id: UUID,
    sector_code: str,
) -> SectorItem:
    """Get a single sector by its code."""
    entry = _TAXONOMY_BY_CODE.get(sector_code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Sector not found")
    return SectorItem(**entry)  # type: ignore[arg-type]
