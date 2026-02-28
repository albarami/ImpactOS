"""FastAPI knowledge flywheel endpoints — MVP-12.

POST /{ws}/libraries/mapping/entries               — create mapping entry
GET  /{ws}/libraries/mapping/entries               — list mapping entries
GET  /{ws}/libraries/mapping/entries/{id}          — get mapping entry
PATCH/{ws}/libraries/mapping/entries/{id}/status   — promote/deprecate (Amend 7)
POST /{ws}/libraries/mapping/versions              — publish mapping version
GET  /{ws}/libraries/mapping/versions              — list mapping versions
GET  /{ws}/libraries/mapping/versions/latest       — latest mapping version

POST /{ws}/libraries/assumptions/entries           — create assumption entry
GET  /{ws}/libraries/assumptions/entries           — list assumption entries
GET  /{ws}/libraries/assumptions/entries/{id}      — get assumption entry
PATCH/{ws}/libraries/assumptions/entries/{id}/status — promote/deprecate
POST /{ws}/libraries/assumptions/versions          — publish assumption version
GET  /{ws}/libraries/assumptions/versions          — list assumption versions
GET  /{ws}/libraries/assumptions/versions/latest   — latest assumption version

POST /{ws}/libraries/patterns                      — create pattern
GET  /{ws}/libraries/patterns                      — list patterns
GET  /{ws}/libraries/patterns/{id}                 — get pattern
PATCH/{ws}/libraries/patterns/{id}/usage           — increment pattern usage
GET  /{ws}/libraries/stats                         — aggregate stats

All 8 amendments enforced. Workspace-scoped routes.
"""

import logging
from enum import StrEnum
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from src.api.dependencies import (
    get_assumption_library_repo,
    get_mapping_library_repo,
    get_scenario_pattern_repo,
)
from src.models.common import new_uuid7
from src.repositories.libraries import (
    AssumptionLibraryRepository,
    MappingLibraryRepository,
    ScenarioPatternRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workspaces", tags=["libraries"])


# ---------------------------------------------------------------------------
# Status enum for validation
# ---------------------------------------------------------------------------


class EntryStatusValue(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateMappingEntryRequest(BaseModel):
    pattern: str
    sector_code: str
    confidence: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    source_engagement_id: str | None = None
    created_by: str | None = None


class MappingEntryResponse(BaseModel):
    entry_id: str
    workspace_id: str
    pattern: str
    sector_code: str
    confidence: float
    usage_count: int
    source_engagement_id: str | None = None
    last_used_at: str | None = None
    tags: list[str]
    created_by: str | None = None
    created_at: str
    status: str


class PatchStatusRequest(BaseModel):
    status: EntryStatusValue


class MappingVersionResponse(BaseModel):
    library_version_id: str
    workspace_id: str
    version: int
    entry_ids: list[str]
    entry_count: int
    published_by: str | None = None
    created_at: str


class CreateAssumptionEntryRequest(BaseModel):
    assumption_type: str
    sector_code: str
    default_value: float
    range_low: float
    range_high: float
    unit: str
    justification: str = ""
    source: str = ""
    source_engagement_id: str | None = None
    confidence: str = "ASSUMED"
    created_by: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("range_high")
    @classmethod
    def validate_range(cls, v: float, info) -> float:  # noqa: ANN001
        if "range_low" in info.data and v < info.data["range_low"]:
            msg = "range_high must be >= range_low"
            raise ValueError(msg)
        return v


class AssumptionEntryResponse(BaseModel):
    entry_id: str
    workspace_id: str
    assumption_type: str
    sector_code: str
    default_value: float
    range_low: float
    range_high: float
    unit: str
    justification: str
    source: str
    source_engagement_id: str | None = None
    usage_count: int
    last_used_at: str | None = None
    confidence: str
    created_by: str | None = None
    created_at: str
    evidence_refs: list[str]
    status: str


class AssumptionVersionResponse(BaseModel):
    library_version_id: str
    workspace_id: str
    version: int
    entry_ids: list[str]
    entry_count: int
    published_by: str | None = None
    created_at: str


class CreatePatternRequest(BaseModel):
    name: str
    description: str = ""
    sector_focus: list[str] = Field(default_factory=list)
    typical_shock_types: list[str] = Field(default_factory=list)
    typical_assumptions: list[str] = Field(default_factory=list)
    recommended_sensitivities: list[str] = Field(default_factory=list)
    recommended_contrarian_angles: list[str] = Field(default_factory=list)
    source_engagement_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = None


class PatternResponse(BaseModel):
    pattern_id: str
    workspace_id: str
    name: str
    description: str
    sector_focus: list[str]
    typical_shock_types: list[str]
    typical_assumptions: list[str]
    recommended_sensitivities: list[str]
    recommended_contrarian_angles: list[str]
    source_engagement_ids: list[str]
    usage_count: int
    tags: list[str]
    created_by: str | None = None
    created_at: str


class LibraryStatsResponse(BaseModel):
    mapping_entries: int
    assumption_entries: int
    scenario_patterns: int
    mapping_versions: int
    assumption_versions: int


# ---------------------------------------------------------------------------
# Mapping Library — Entries
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/libraries/mapping/entries",
    status_code=201,
    response_model=MappingEntryResponse,
)
async def create_mapping_entry(
    workspace_id: UUID,
    body: CreateMappingEntryRequest,
    repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
) -> MappingEntryResponse:
    entry_id = new_uuid7()
    row = await repo.create_entry(
        entry_id=entry_id,
        workspace_id=workspace_id,
        pattern=body.pattern,
        sector_code=body.sector_code,
        confidence=body.confidence,
        tags=body.tags,
        source_engagement_id=(
            UUID(body.source_engagement_id)
            if body.source_engagement_id else None
        ),
        created_by=(
            UUID(body.created_by) if body.created_by else None
        ),
        status="DRAFT",
    )
    return _mapping_entry_response(row)


@router.get(
    "/{workspace_id}/libraries/mapping/entries",
    response_model=list[MappingEntryResponse],
)
async def list_mapping_entries(
    workspace_id: UUID,
    sector_code: str | None = Query(None),
    repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
) -> list[MappingEntryResponse]:
    rows = await repo.get_entries_by_workspace(
        workspace_id, sector_code=sector_code,
    )
    return [_mapping_entry_response(r) for r in rows]


@router.get(
    "/{workspace_id}/libraries/mapping/entries/{entry_id}",
    response_model=MappingEntryResponse,
)
async def get_mapping_entry(
    workspace_id: UUID,
    entry_id: UUID,
    repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
) -> MappingEntryResponse:
    row = await repo.get_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return _mapping_entry_response(row)


@router.patch(
    "/{workspace_id}/libraries/mapping/entries/{entry_id}/status",
    response_model=MappingEntryResponse,
)
async def patch_mapping_entry_status(
    workspace_id: UUID,
    entry_id: UUID,
    body: PatchStatusRequest,
    repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
) -> MappingEntryResponse:
    """Amendment 7: steward-gated status promotion."""
    row = await repo.update_status(entry_id, status=body.status.value)
    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return _mapping_entry_response(row)


# ---------------------------------------------------------------------------
# Mapping Library — Versions
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/libraries/mapping/versions",
    status_code=201,
    response_model=MappingVersionResponse,
)
async def publish_mapping_version(
    workspace_id: UUID,
    repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
) -> MappingVersionResponse:
    """Publish a snapshot. Only PUBLISHED entries (Amendment 7).

    Version = MAX(workspace) + 1 (Amendment 1).
    """
    # Get PUBLISHED entries
    all_entries = await repo.get_entries_by_workspace(workspace_id)
    published_entries = [e for e in all_entries if e.status == "PUBLISHED"]
    published_ids = [e.entry_id for e in published_entries]

    # Auto-increment version
    latest = await repo.get_latest_version(workspace_id)
    next_version = (latest.version + 1) if latest else 1

    row = await repo.create_version(
        library_version_id=new_uuid7(),
        workspace_id=workspace_id,
        version=next_version,
        entry_ids=[str(eid) for eid in published_ids],
        entry_count=len(published_ids),
    )
    return _mapping_version_response(row)


@router.get(
    "/{workspace_id}/libraries/mapping/versions",
    response_model=list[MappingVersionResponse],
)
async def list_mapping_versions(
    workspace_id: UUID,
    repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
) -> list[MappingVersionResponse]:
    rows = await repo.get_versions_by_workspace(workspace_id)
    return [_mapping_version_response(r) for r in rows]


@router.get(
    "/{workspace_id}/libraries/mapping/versions/latest",
    response_model=MappingVersionResponse,
)
async def get_latest_mapping_version(
    workspace_id: UUID,
    repo: MappingLibraryRepository = Depends(get_mapping_library_repo),
) -> MappingVersionResponse:
    row = await repo.get_latest_version(workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No versions found.")
    return _mapping_version_response(row)


# ---------------------------------------------------------------------------
# Assumption Library — Entries
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/libraries/assumptions/entries",
    status_code=201,
    response_model=AssumptionEntryResponse,
)
async def create_assumption_entry(
    workspace_id: UUID,
    body: CreateAssumptionEntryRequest,
    repo: AssumptionLibraryRepository = Depends(get_assumption_library_repo),
) -> AssumptionEntryResponse:
    entry_id = new_uuid7()
    row = await repo.create_entry(
        entry_id=entry_id,
        workspace_id=workspace_id,
        assumption_type=body.assumption_type,
        sector_code=body.sector_code,
        default_value=body.default_value,
        range_low=body.range_low,
        range_high=body.range_high,
        unit=body.unit,
        justification=body.justification,
        source=body.source,
        source_engagement_id=(
            UUID(body.source_engagement_id)
            if body.source_engagement_id else None
        ),
        confidence=body.confidence,
        created_by=(
            UUID(body.created_by) if body.created_by else None
        ),
        evidence_refs=[UUID(r) for r in body.evidence_refs],
        status="DRAFT",
    )
    return _assumption_entry_response(row)


@router.get(
    "/{workspace_id}/libraries/assumptions/entries",
    response_model=list[AssumptionEntryResponse],
)
async def list_assumption_entries(
    workspace_id: UUID,
    assumption_type: str | None = Query(None),
    sector_code: str | None = Query(None),
    repo: AssumptionLibraryRepository = Depends(get_assumption_library_repo),
) -> list[AssumptionEntryResponse]:
    rows = await repo.get_entries_by_workspace(
        workspace_id,
        assumption_type=assumption_type,
        sector_code=sector_code,
    )
    return [_assumption_entry_response(r) for r in rows]


@router.get(
    "/{workspace_id}/libraries/assumptions/entries/{entry_id}",
    response_model=AssumptionEntryResponse,
)
async def get_assumption_entry(
    workspace_id: UUID,
    entry_id: UUID,
    repo: AssumptionLibraryRepository = Depends(get_assumption_library_repo),
) -> AssumptionEntryResponse:
    row = await repo.get_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return _assumption_entry_response(row)


@router.patch(
    "/{workspace_id}/libraries/assumptions/entries/{entry_id}/status",
    response_model=AssumptionEntryResponse,
)
async def patch_assumption_entry_status(
    workspace_id: UUID,
    entry_id: UUID,
    body: PatchStatusRequest,
    repo: AssumptionLibraryRepository = Depends(get_assumption_library_repo),
) -> AssumptionEntryResponse:
    """Amendment 7: steward-gated status promotion."""
    row = await repo.update_status(entry_id, status=body.status.value)
    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return _assumption_entry_response(row)


# ---------------------------------------------------------------------------
# Assumption Library — Versions
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/libraries/assumptions/versions",
    status_code=201,
    response_model=AssumptionVersionResponse,
)
async def publish_assumption_version(
    workspace_id: UUID,
    repo: AssumptionLibraryRepository = Depends(get_assumption_library_repo),
) -> AssumptionVersionResponse:
    """Publish snapshot. Only PUBLISHED entries (Amendment 7)."""
    all_entries = await repo.get_entries_by_workspace(workspace_id)
    published_entries = [e for e in all_entries if e.status == "PUBLISHED"]
    published_ids = [e.entry_id for e in published_entries]

    latest = await repo.get_latest_version(workspace_id)
    next_version = (latest.version + 1) if latest else 1

    row = await repo.create_version(
        library_version_id=new_uuid7(),
        workspace_id=workspace_id,
        version=next_version,
        entry_ids=[str(eid) for eid in published_ids],
        entry_count=len(published_ids),
    )
    return _assumption_version_response(row)


@router.get(
    "/{workspace_id}/libraries/assumptions/versions",
    response_model=list[AssumptionVersionResponse],
)
async def list_assumption_versions(
    workspace_id: UUID,
    repo: AssumptionLibraryRepository = Depends(get_assumption_library_repo),
) -> list[AssumptionVersionResponse]:
    rows = await repo.get_versions_by_workspace(workspace_id)
    return [_assumption_version_response(r) for r in rows]


@router.get(
    "/{workspace_id}/libraries/assumptions/versions/latest",
    response_model=AssumptionVersionResponse,
)
async def get_latest_assumption_version(
    workspace_id: UUID,
    repo: AssumptionLibraryRepository = Depends(get_assumption_library_repo),
) -> AssumptionVersionResponse:
    row = await repo.get_latest_version(workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No versions found.")
    return _assumption_version_response(row)


# ---------------------------------------------------------------------------
# Scenario Patterns
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/libraries/patterns",
    status_code=201,
    response_model=PatternResponse,
)
async def create_pattern(
    workspace_id: UUID,
    body: CreatePatternRequest,
    repo: ScenarioPatternRepository = Depends(get_scenario_pattern_repo),
) -> PatternResponse:
    pattern_id = new_uuid7()
    row = await repo.create(
        pattern_id=pattern_id,
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        sector_focus=body.sector_focus,
        typical_shock_types=body.typical_shock_types,
        typical_assumptions=body.typical_assumptions,
        recommended_sensitivities=body.recommended_sensitivities,
        recommended_contrarian_angles=body.recommended_contrarian_angles,
        source_engagement_ids=[
            UUID(s) for s in body.source_engagement_ids
        ] if body.source_engagement_ids else [],
        tags=body.tags,
        created_by=(
            UUID(body.created_by) if body.created_by else None
        ),
    )
    return _pattern_response(row)


@router.get(
    "/{workspace_id}/libraries/patterns",
    response_model=list[PatternResponse],
)
async def list_patterns(
    workspace_id: UUID,
    repo: ScenarioPatternRepository = Depends(get_scenario_pattern_repo),
) -> list[PatternResponse]:
    rows = await repo.get_by_workspace(workspace_id)
    return [_pattern_response(r) for r in rows]


@router.get(
    "/{workspace_id}/libraries/patterns/{pattern_id}",
    response_model=PatternResponse,
)
async def get_pattern(
    workspace_id: UUID,
    pattern_id: UUID,
    repo: ScenarioPatternRepository = Depends(get_scenario_pattern_repo),
) -> PatternResponse:
    row = await repo.get(pattern_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern not found.")
    return _pattern_response(row)


@router.patch(
    "/{workspace_id}/libraries/patterns/{pattern_id}/usage",
    response_model=PatternResponse,
)
async def increment_pattern_usage(
    workspace_id: UUID,
    pattern_id: UUID,
    repo: ScenarioPatternRepository = Depends(get_scenario_pattern_repo),
) -> PatternResponse:
    row = await repo.get(pattern_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern not found.")
    updated = await repo.update_usage(
        pattern_id, usage_count=row.usage_count + 1,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Pattern not found.")
    return _pattern_response(updated)


# ---------------------------------------------------------------------------
# Aggregate Stats
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/libraries/stats",
    response_model=LibraryStatsResponse,
)
async def get_library_stats(
    workspace_id: UUID,
    mapping_repo: MappingLibraryRepository = Depends(
        get_mapping_library_repo,
    ),
    assumption_repo: AssumptionLibraryRepository = Depends(
        get_assumption_library_repo,
    ),
    pattern_repo: ScenarioPatternRepository = Depends(
        get_scenario_pattern_repo,
    ),
) -> LibraryStatsResponse:
    mapping_entries = await mapping_repo.get_entries_by_workspace(workspace_id)
    assumption_entries = await assumption_repo.get_entries_by_workspace(
        workspace_id,
    )
    patterns = await pattern_repo.get_by_workspace(workspace_id)
    mapping_versions = await mapping_repo.get_versions_by_workspace(
        workspace_id,
    )
    assumption_versions = await assumption_repo.get_versions_by_workspace(
        workspace_id,
    )

    return LibraryStatsResponse(
        mapping_entries=len(mapping_entries),
        assumption_entries=len(assumption_entries),
        scenario_patterns=len(patterns),
        mapping_versions=len(mapping_versions),
        assumption_versions=len(assumption_versions),
    )


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _mapping_entry_response(row) -> MappingEntryResponse:  # noqa: ANN001
    return MappingEntryResponse(
        entry_id=str(row.entry_id),
        workspace_id=str(row.workspace_id),
        pattern=row.pattern,
        sector_code=row.sector_code,
        confidence=row.confidence,
        usage_count=row.usage_count,
        source_engagement_id=(
            str(row.source_engagement_id)
            if row.source_engagement_id else None
        ),
        last_used_at=(
            str(row.last_used_at) if row.last_used_at else None
        ),
        tags=row.tags or [],
        created_by=str(row.created_by) if row.created_by else None,
        created_at=str(row.created_at),
        status=row.status,
    )


def _mapping_version_response(row) -> MappingVersionResponse:  # noqa: ANN001
    return MappingVersionResponse(
        library_version_id=str(row.library_version_id),
        workspace_id=str(row.workspace_id),
        version=row.version,
        entry_ids=row.entry_ids or [],
        entry_count=row.entry_count,
        published_by=(
            str(row.published_by) if row.published_by else None
        ),
        created_at=str(row.created_at),
    )


def _assumption_entry_response(row) -> AssumptionEntryResponse:  # noqa: ANN001
    return AssumptionEntryResponse(
        entry_id=str(row.entry_id),
        workspace_id=str(row.workspace_id),
        assumption_type=row.assumption_type,
        sector_code=row.sector_code,
        default_value=row.default_value,
        range_low=row.range_low,
        range_high=row.range_high,
        unit=row.unit,
        justification=row.justification or "",
        source=row.source or "",
        source_engagement_id=(
            str(row.source_engagement_id)
            if row.source_engagement_id else None
        ),
        usage_count=row.usage_count,
        last_used_at=(
            str(row.last_used_at) if row.last_used_at else None
        ),
        confidence=row.confidence,
        created_by=str(row.created_by) if row.created_by else None,
        created_at=str(row.created_at),
        evidence_refs=[str(r) for r in (row.evidence_refs or [])],
        status=row.status,
    )


def _assumption_version_response(
    row,  # noqa: ANN001
) -> AssumptionVersionResponse:
    return AssumptionVersionResponse(
        library_version_id=str(row.library_version_id),
        workspace_id=str(row.workspace_id),
        version=row.version,
        entry_ids=row.entry_ids or [],
        entry_count=row.entry_count,
        published_by=(
            str(row.published_by) if row.published_by else None
        ),
        created_at=str(row.created_at),
    )


def _pattern_response(row) -> PatternResponse:  # noqa: ANN001
    return PatternResponse(
        pattern_id=str(row.pattern_id),
        workspace_id=str(row.workspace_id),
        name=row.name,
        description=row.description or "",
        sector_focus=row.sector_focus or [],
        typical_shock_types=row.typical_shock_types or [],
        typical_assumptions=row.typical_assumptions or [],
        recommended_sensitivities=row.recommended_sensitivities or [],
        recommended_contrarian_angles=(
            row.recommended_contrarian_angles or []
        ),
        source_engagement_ids=[
            str(s) for s in (row.source_engagement_ids or [])
        ],
        usage_count=row.usage_count,
        tags=row.tags or [],
        created_by=str(row.created_by) if row.created_by else None,
        created_at=str(row.created_at),
    )
