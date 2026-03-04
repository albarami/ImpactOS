"""Tests for workspace-scoped AssumptionRepository methods."""

import pytest
from uuid_extensions import uuid7

from src.db.tables import AssumptionRow, WorkspaceRow
from src.models.common import utc_now
from src.repositories.governance import AssumptionRepository

pytestmark = pytest.mark.anyio


async def _create_workspace(session, workspace_id=None) -> WorkspaceRow:
    """Helper to create a workspace row."""
    now = utc_now()
    ws = WorkspaceRow(
        workspace_id=workspace_id or uuid7(),
        client_name="Test Client",
        engagement_code="ENG-001",
        classification="INTERNAL",
        description="Test workspace",
        created_by=uuid7(),
        created_at=now,
        updated_at=now,
    )
    session.add(ws)
    await session.flush()
    return ws


async def _create_assumption(
    session, workspace_id=None, status="DRAFT", created_at=None,
) -> AssumptionRow:
    """Helper to create an assumption row."""
    now = created_at or utc_now()
    row = AssumptionRow(
        assumption_id=uuid7(),
        type="growth_rate",
        value=3.5,
        range_json=None,
        units="percent",
        justification="Test assumption",
        evidence_refs=[],
        workspace_id=workspace_id,
        status=status,
        approved_by=None,
        approved_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


# --- get_for_workspace tests ---


async def test_get_for_workspace_returns_matching(db_session):
    """Get by id and workspace returns the assumption."""
    ws = await _create_workspace(db_session)
    row = await _create_assumption(db_session, workspace_id=ws.workspace_id)

    repo = AssumptionRepository(db_session)
    result = await repo.get_for_workspace(row.assumption_id, ws.workspace_id)
    assert result is not None
    assert result.assumption_id == row.assumption_id


async def test_get_for_workspace_returns_none_wrong_workspace(db_session):
    """Get by id but wrong workspace returns None."""
    ws_a = await _create_workspace(db_session)
    ws_b = await _create_workspace(db_session)
    row = await _create_assumption(db_session, workspace_id=ws_a.workspace_id)

    repo = AssumptionRepository(db_session)
    result = await repo.get_for_workspace(row.assumption_id, ws_b.workspace_id)
    assert result is None


async def test_get_for_workspace_returns_none_null_workspace(db_session):
    """Legacy row with NULL workspace_id returns None."""
    ws = await _create_workspace(db_session)
    row = await _create_assumption(db_session, workspace_id=None)

    repo = AssumptionRepository(db_session)
    result = await repo.get_for_workspace(row.assumption_id, ws.workspace_id)
    assert result is None


# --- list_by_workspace tests ---


async def test_list_by_workspace_returns_only_workspace_rows(db_session):
    """List returns only rows belonging to the requested workspace."""
    ws_a = await _create_workspace(db_session)
    ws_b = await _create_workspace(db_session)
    a1 = await _create_assumption(db_session, workspace_id=ws_a.workspace_id)
    await _create_assumption(db_session, workspace_id=ws_b.workspace_id)

    repo = AssumptionRepository(db_session)
    rows, total = await repo.list_by_workspace(ws_a.workspace_id)
    assert total == 1
    assert len(rows) == 1
    assert rows[0].assumption_id == a1.assumption_id


async def test_list_by_workspace_excludes_null_workspace(db_session):
    """Legacy rows with NULL workspace_id are not returned."""
    ws = await _create_workspace(db_session)
    await _create_assumption(db_session, workspace_id=ws.workspace_id)
    await _create_assumption(db_session, workspace_id=None)  # legacy

    repo = AssumptionRepository(db_session)
    rows, total = await repo.list_by_workspace(ws.workspace_id)
    assert total == 1
    assert len(rows) == 1


async def test_list_by_workspace_filters_by_status(db_session):
    """Status filter narrows results."""
    ws = await _create_workspace(db_session)
    await _create_assumption(db_session, workspace_id=ws.workspace_id, status="DRAFT")
    await _create_assumption(db_session, workspace_id=ws.workspace_id, status="APPROVED")

    repo = AssumptionRepository(db_session)
    rows, total = await repo.list_by_workspace(ws.workspace_id, status="DRAFT")
    assert total == 1
    assert len(rows) == 1
    assert rows[0].status == "DRAFT"


async def test_list_by_workspace_orders_by_created_at_desc(db_session):
    """Results are ordered by created_at DESC, assumption_id DESC."""
    from datetime import timedelta
    ws = await _create_workspace(db_session)
    now = utc_now()
    older = await _create_assumption(
        db_session, workspace_id=ws.workspace_id,
        created_at=now - timedelta(hours=1),
    )
    newer = await _create_assumption(
        db_session, workspace_id=ws.workspace_id,
        created_at=now,
    )

    repo = AssumptionRepository(db_session)
    rows, total = await repo.list_by_workspace(ws.workspace_id)
    assert total == 2
    assert rows[0].assumption_id == newer.assumption_id
    assert rows[1].assumption_id == older.assumption_id


async def test_list_by_workspace_paginates(db_session):
    """Pagination works correctly with limit and offset."""
    ws = await _create_workspace(db_session)
    from datetime import timedelta
    now = utc_now()
    # Create 5 rows with distinct timestamps
    for i in range(5):
        await _create_assumption(
            db_session, workspace_id=ws.workspace_id,
            created_at=now - timedelta(minutes=5 - i),
        )

    repo = AssumptionRepository(db_session)
    page1, total1 = await repo.list_by_workspace(ws.workspace_id, limit=2, offset=0)
    assert total1 == 5
    assert len(page1) == 2

    page2, total2 = await repo.list_by_workspace(ws.workspace_id, limit=2, offset=2)
    assert total2 == 5
    assert len(page2) == 2

    page3, total3 = await repo.list_by_workspace(ws.workspace_id, limit=2, offset=4)
    assert total3 == 5
    assert len(page3) == 1

    # No overlap between pages
    all_ids = [r.assumption_id for r in page1 + page2 + page3]
    assert len(set(all_ids)) == 5


async def test_list_by_workspace_returns_total_count(db_session):
    """Total count reflects all matching rows, not just the page."""
    ws = await _create_workspace(db_session)
    for _ in range(7):
        await _create_assumption(db_session, workspace_id=ws.workspace_id)

    repo = AssumptionRepository(db_session)
    rows, total = await repo.list_by_workspace(ws.workspace_id, limit=3, offset=0)
    assert total == 7
    assert len(rows) == 3
