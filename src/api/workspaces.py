"""B-1: Workspace CRUD endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_workspace_repo
from src.models.common import DataClassification, new_uuid7
from src.repositories.workspace import WorkspaceRepository

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=255)
    engagement_code: str = Field(min_length=1, max_length=100)
    classification: DataClassification = DataClassification.CONFIDENTIAL
    description: str = Field(default="", max_length=2000)
    created_by: UUID


class UpdateWorkspaceRequest(BaseModel):
    client_name: str | None = Field(default=None, min_length=1, max_length=255)
    engagement_code: str | None = Field(default=None, min_length=1, max_length=100)
    classification: DataClassification | None = None
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceResponse(BaseModel):
    workspace_id: str
    client_name: str
    engagement_code: str
    classification: str
    description: str
    created_by: str
    created_at: str
    updated_at: str


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceResponse]
    total: int


def _row_to_response(row: object) -> WorkspaceResponse:
    return WorkspaceResponse(
        workspace_id=str(row.workspace_id),
        client_name=row.client_name,
        engagement_code=row.engagement_code,
        classification=row.classification,
        description=row.description,
        created_by=str(row.created_by),
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.post("", status_code=201, response_model=WorkspaceResponse)
async def create_workspace(
    body: CreateWorkspaceRequest,
    repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> WorkspaceResponse:
    row = await repo.create(
        workspace_id=new_uuid7(),
        client_name=body.client_name,
        engagement_code=body.engagement_code,
        classification=body.classification,
        description=body.description,
        created_by=body.created_by,
    )
    return _row_to_response(row)


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> WorkspaceListResponse:
    rows = await repo.list_all()
    return WorkspaceListResponse(
        items=[_row_to_response(r) for r in rows],
        total=len(rows),
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> WorkspaceResponse:
    row = await repo.get(workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _row_to_response(row)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    body: UpdateWorkspaceRequest,
    repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> WorkspaceResponse:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    row = await repo.update(workspace_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _row_to_response(row)
