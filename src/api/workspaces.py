"""B-1: Workspace CRUD endpoints — Sprint 10 auth hardening.

All endpoints require authentication via get_current_principal.
Workspace-scoped reads/mutations require workspace membership.
Workspace mutation (PUT) requires manager or admin role.
created_by is set from the authenticated principal, not the request body.
"""


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import (
    AuthPrincipal,
    WorkspaceMember,
    get_current_principal,
    require_role,
    require_workspace_member,
)
from src.api.dependencies import get_workspace_repo
from src.db.session import get_async_session
from src.db.tables import WorkspaceMembershipRow
from src.models.common import DataClassification, new_uuid7, utc_now
from src.repositories.workspace import WorkspaceRepository

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=255)
    engagement_code: str = Field(min_length=1, max_length=100)
    classification: DataClassification = DataClassification.CONFIDENTIAL
    description: str = Field(default="", max_length=2000)


class UpdateWorkspaceRequest(BaseModel):
    client_name: str | None = Field(
        default=None, min_length=1, max_length=255,
    )
    engagement_code: str | None = Field(
        default=None, min_length=1, max_length=100,
    )
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
    principal: AuthPrincipal = Depends(get_current_principal),
    repo: WorkspaceRepository = Depends(get_workspace_repo),
    session: AsyncSession = Depends(get_async_session),
) -> WorkspaceResponse:
    """Create workspace. created_by is set from authenticated principal."""
    ws_id = new_uuid7()
    row = await repo.create(
        workspace_id=ws_id,
        client_name=body.client_name,
        engagement_code=body.engagement_code,
        classification=body.classification,
        description=body.description,
        created_by=principal.user_id,
    )

    now = utc_now()
    membership = WorkspaceMembershipRow(
        workspace_id=ws_id,
        user_id=principal.user_id,
        role="admin",
        created_at=now,
        created_by=principal.user_id,
    )
    session.add(membership)
    await session.flush()

    return _row_to_response(row)


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    principal: AuthPrincipal = Depends(get_current_principal),
    repo: WorkspaceRepository = Depends(get_workspace_repo),
    session: AsyncSession = Depends(get_async_session),
) -> WorkspaceListResponse:
    """List workspaces the authenticated user is a member of."""
    from sqlalchemy import select

    stmt = select(WorkspaceMembershipRow.workspace_id).where(
        WorkspaceMembershipRow.user_id == principal.user_id,
    )
    result = await session.execute(stmt)
    member_ws_ids = {row[0] for row in result.all()}

    all_rows = await repo.list_all()
    visible = [r for r in all_rows if r.workspace_id in member_ws_ids]

    return WorkspaceListResponse(
        items=[_row_to_response(r) for r in visible],
        total=len(visible),
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    member: WorkspaceMember = Depends(require_workspace_member),
    repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> WorkspaceResponse:
    """Get workspace detail — requires workspace membership."""
    row = await repo.get(member.workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _row_to_response(row)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    body: UpdateWorkspaceRequest,
    member: WorkspaceMember = Depends(
        require_role("manager", "admin"),
    ),
    repo: WorkspaceRepository = Depends(get_workspace_repo),
) -> WorkspaceResponse:
    """Update workspace — requires manager or admin role."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")
    null_fields = [k for k, v in updates.items() if v is None]
    if null_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Null not allowed for: {', '.join(null_fields)}",
        )
    row = await repo.update(member.workspace_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _row_to_response(row)
