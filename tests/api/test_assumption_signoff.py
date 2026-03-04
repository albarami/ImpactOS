"""Tests for Sprint 19 assumption sign-off collaboration endpoints."""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.db.session import get_async_session
from src.db.tables import AssumptionRow, WorkspaceMembershipRow, WorkspaceRow
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS_A = UUID("00000000-0000-7000-8000-000000000010")  # matches default client fixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_workspace(session: AsyncSession, ws_id: UUID) -> None:
    """Create workspace if it doesn't exist."""
    from sqlalchemy import select
    result = await session.execute(
        select(WorkspaceRow).where(WorkspaceRow.workspace_id == ws_id)
    )
    if result.scalar_one_or_none() is None:
        now = utc_now()
        session.add(WorkspaceRow(
            workspace_id=ws_id, client_name="Test", engagement_code="E",
            classification="INTERNAL", description="",
            created_by=uuid7(), created_at=now, updated_at=now,
        ))
        await session.flush()


async def _create_assumption_row(
    session: AsyncSession, workspace_id: UUID | None = None,
    status: str = "DRAFT", range_json: dict | None = None,
) -> AssumptionRow:
    """Insert an assumption row directly in DB."""
    now = utc_now()
    row = AssumptionRow(
        assumption_id=uuid7(), type="growth_rate", value=3.5,
        range_json=range_json, units="percent", justification="test",
        evidence_refs=[], workspace_id=workspace_id,
        status=status, approved_by=None, approved_at=None,
        created_at=now, updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# List endpoint tests
# ---------------------------------------------------------------------------

async def test_list_assumptions_empty_workspace(client, db_session):
    """GET list on empty workspace returns 200 with empty items."""
    await _seed_workspace(db_session, WS_A)
    resp = await client.get(f"/v1/workspaces/{WS_A}/governance/assumptions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_assumptions_returns_workspace_scoped(client, db_session):
    """Only assumptions for the requested workspace are returned."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(db_session, workspace_id=WS_A)

    ws_b = uuid7()
    await _seed_workspace(db_session, ws_b)
    await _create_assumption_row(db_session, workspace_id=ws_b)

    resp = await client.get(f"/v1/workspaces/{WS_A}/governance/assumptions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["assumption_id"] == str(row.assumption_id)


async def test_list_assumptions_filters_by_status(client, db_session):
    """Status query param filters results."""
    await _seed_workspace(db_session, WS_A)
    await _create_assumption_row(db_session, workspace_id=WS_A, status="DRAFT")
    await _create_assumption_row(db_session, workspace_id=WS_A, status="APPROVED",
                                  range_json={"min": 1.0, "max": 5.0})

    resp = await client.get(
        f"/v1/workspaces/{WS_A}/governance/assumptions",
        params={"status": "DRAFT"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "DRAFT"


async def test_list_assumptions_paginates(client, db_session):
    """Pagination returns correct has_more and page size."""
    await _seed_workspace(db_session, WS_A)
    for i in range(5):
        await _create_assumption_row(db_session, workspace_id=WS_A)

    resp = await client.get(
        f"/v1/workspaces/{WS_A}/governance/assumptions",
        params={"limit": 2, "offset": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["has_more"] is True


async def test_list_assumptions_invalid_pagination_422(client, db_session):
    """limit > 100 returns 422 with reason code."""
    await _seed_workspace(db_session, WS_A)
    resp = await client.get(
        f"/v1/workspaces/{WS_A}/governance/assumptions",
        params={"limit": 200},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["reason_code"] == "ASSUMPTION_INVALID_PAGINATION"


async def test_list_assumptions_hides_null_workspace(client, db_session):
    """Legacy rows with NULL workspace_id are not returned."""
    await _seed_workspace(db_session, WS_A)
    await _create_assumption_row(db_session, workspace_id=None)

    resp = await client.get(f"/v1/workspaces/{WS_A}/governance/assumptions")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Detail endpoint tests
# ---------------------------------------------------------------------------

async def test_get_assumption_detail(client, db_session):
    """GET detail returns full assumption with all fields."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(db_session, workspace_id=WS_A)

    resp = await client.get(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assumption_id"] == str(row.assumption_id)
    assert data["type"] == "growth_rate"
    assert data["status"] == "DRAFT"
    assert "evidence_refs" in data


async def test_get_assumption_detail_404_wrong_workspace(client, db_session):
    """Detail for assumption in different workspace returns 404."""
    await _seed_workspace(db_session, WS_A)
    ws_b = uuid7()
    await _seed_workspace(db_session, ws_b)
    row = await _create_assumption_row(db_session, workspace_id=ws_b)

    resp = await client.get(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}"
    )
    assert resp.status_code == 404


async def test_get_assumption_detail_404_null_workspace(client, db_session):
    """Detail for legacy row (NULL workspace_id) returns 404."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(db_session, workspace_id=None)

    resp = await client.get(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create tests
# ---------------------------------------------------------------------------

async def test_create_assumption_sets_workspace_id(client, db_session):
    """POST create persists workspace_id from path."""
    await _seed_workspace(db_session, WS_A)
    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions",
        json={"type": "IMPORT_SHARE", "value": 3.5, "units": "percent",
              "justification": "Test"},
    )
    assert resp.status_code == 201
    aid = UUID(resp.json()["assumption_id"])

    # Verify in DB
    from sqlalchemy import select
    result = await db_session.execute(
        select(AssumptionRow).where(AssumptionRow.assumption_id == aid)
    )
    row = result.scalar_one()
    assert row.workspace_id == WS_A


# ---------------------------------------------------------------------------
# Approve tests
# ---------------------------------------------------------------------------

async def test_approve_requires_manager_role(db_session):
    """Analyst role gets 403 on approve."""
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as unauthed:
        token_resp = await unauthed.post(
            "/v1/auth/login", json={"username": "analyst", "password": "any"},
        )
        token = token_resp.json()["token"]

        # Seed workspace + membership for the analyst user
        analyst_id = UUID("00000000-0000-7000-8000-000000000001")
        await _seed_workspace(db_session, WS_A)
        now = utc_now()
        db_session.add(WorkspaceMembershipRow(
            workspace_id=WS_A, user_id=analyst_id,
            role="analyst", created_at=now, created_by=analyst_id,
        ))
        await db_session.flush()

        row = await _create_assumption_row(db_session, workspace_id=WS_A)

        resp = await unauthed.post(
            f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
            json={"range_min": 1.0, "range_max": 5.0, "actor": str(uuid7())},
        )
        assert resp.status_code == 403

    app.dependency_overrides.clear()


async def test_approve_workspace_scoped_404(client, db_session):
    """Approve from wrong workspace returns 404."""
    await _seed_workspace(db_session, WS_A)
    ws_b = uuid7()
    await _seed_workspace(db_session, ws_b)
    row = await _create_assumption_row(db_session, workspace_id=ws_b)

    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/approve",
        json={"range_min": 1.0, "range_max": 5.0, "actor": str(uuid7())},
    )
    assert resp.status_code == 404


async def test_approve_missing_range_422(client, db_session):
    """Approve without range returns 422 ASSUMPTION_RANGE_REQUIRED."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(db_session, workspace_id=WS_A)

    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/approve",
        json={"actor": str(uuid7())},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["reason_code"] == "ASSUMPTION_RANGE_REQUIRED"


async def test_approve_non_draft_409(client, db_session):
    """Approve non-DRAFT returns 409 ASSUMPTION_NOT_DRAFT."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(
        db_session, workspace_id=WS_A, status="APPROVED",
        range_json={"min": 1.0, "max": 5.0},
    )

    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/approve",
        json={"range_min": 1.0, "range_max": 5.0, "actor": str(uuid7())},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["reason_code"] == "ASSUMPTION_NOT_DRAFT"


async def test_approve_happy_path(client, db_session):
    """Manager approves DRAFT -> 200, status=APPROVED."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(db_session, workspace_id=WS_A)
    actor = uuid7()

    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/approve",
        json={"range_min": 1.0, "range_max": 5.0, "actor": str(actor)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "APPROVED"
    assert data["range_min"] == 1.0
    assert data["range_max"] == 5.0


# ---------------------------------------------------------------------------
# Reject tests
# ---------------------------------------------------------------------------

async def test_reject_requires_manager_role(db_session):
    """Analyst role gets 403 on reject."""
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as unauthed:
        token_resp = await unauthed.post(
            "/v1/auth/login", json={"username": "analyst", "password": "any"},
        )
        token = token_resp.json()["token"]

        analyst_id = UUID("00000000-0000-7000-8000-000000000001")
        await _seed_workspace(db_session, WS_A)
        now = utc_now()
        # Check if membership already exists
        from sqlalchemy import select
        existing = await db_session.execute(
            select(WorkspaceMembershipRow).where(
                WorkspaceMembershipRow.workspace_id == WS_A,
                WorkspaceMembershipRow.user_id == analyst_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            db_session.add(WorkspaceMembershipRow(
                workspace_id=WS_A, user_id=analyst_id,
                role="analyst", created_at=now, created_by=analyst_id,
            ))
            await db_session.flush()

        row = await _create_assumption_row(db_session, workspace_id=WS_A)

        resp = await unauthed.post(
            f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/reject",
            headers={"Authorization": f"Bearer {token}"},
            json={"actor": str(uuid7())},
        )
        assert resp.status_code == 403

    app.dependency_overrides.clear()


async def test_reject_workspace_scoped_404(client, db_session):
    """Reject from wrong workspace returns 404."""
    await _seed_workspace(db_session, WS_A)
    ws_b = uuid7()
    await _seed_workspace(db_session, ws_b)
    row = await _create_assumption_row(db_session, workspace_id=ws_b)

    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/reject",
        json={"actor": str(uuid7())},
    )
    assert resp.status_code == 404


async def test_reject_non_draft_409(client, db_session):
    """Reject non-DRAFT returns 409 ASSUMPTION_NOT_DRAFT."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(
        db_session, workspace_id=WS_A, status="APPROVED",
        range_json={"min": 1.0, "max": 5.0},
    )

    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/reject",
        json={"actor": str(uuid7())},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["reason_code"] == "ASSUMPTION_NOT_DRAFT"


async def test_reject_happy_path(client, db_session):
    """Manager rejects DRAFT -> 200, status=REJECTED."""
    await _seed_workspace(db_session, WS_A)
    row = await _create_assumption_row(db_session, workspace_id=WS_A)

    resp = await client.post(
        f"/v1/workspaces/{WS_A}/governance/assumptions/{row.assumption_id}/reject",
        json={"actor": str(uuid7())},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assumption_id"] == str(row.assumption_id)
    assert data["status"] == "REJECTED"
