"""Tests for PortfolioRepository — workspace scoping, CRUD, pagination, idempotency."""

import pytest
from sqlalchemy.exc import IntegrityError
from uuid_extensions import uuid7

from src.db.tables import ModelVersionRow, PortfolioOptimizationRow, WorkspaceRow
from src.models.common import utc_now
from src.repositories.portfolio import PortfolioRepository

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_workspace(session, workspace_id=None) -> WorkspaceRow:
    """Create a minimal workspace row."""
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


async def _seed_model(session, workspace_id) -> ModelVersionRow:  # noqa: ARG001
    """Create a minimal model version row."""
    mv = ModelVersionRow(
        model_version_id=uuid7(),
        base_year=2023,
        source="test-source",
        sector_count=45,
        checksum="sha256:model_abc",
        provenance_class="official",
        created_at=utc_now(),
    )
    session.add(mv)
    await session.flush()
    return mv


async def _create_portfolio(
    repo: PortfolioRepository,
    workspace_id,
    model_version_id,
    *,
    config_hash: str = "sha256:cfg_default",
) -> PortfolioOptimizationRow:
    """Create a portfolio optimization row through the repository."""
    return await repo.create(
        portfolio_id=uuid7(),
        workspace_id=workspace_id,
        model_version_id=model_version_id,
        optimization_version="1.0.0",
        config_json={"objective": "gdp", "budget": 500_000},
        config_hash=config_hash,
        objective_metric="gdp",
        cost_metric="cost_sar",
        budget=500_000.0,
        min_selected=2,
        max_selected=10,
        candidate_run_ids_json=[str(uuid7()) for _ in range(5)],
        selected_run_ids_json=[str(uuid7()) for _ in range(3)],
        result_json={"frontier": [{"x": 1, "y": 2}], "selected": 3},
        result_checksum="sha256:result_abc",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_create_and_get(db_session):
    """Create -> get -> verify all fields match."""
    ws = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws.workspace_id)
    repo = PortfolioRepository(db_session)

    portfolio_id = uuid7()
    config_json = {"objective": "gdp", "budget": 1_000_000}
    candidate_ids = [str(uuid7()) for _ in range(4)]
    selected_ids = [str(uuid7()) for _ in range(2)]
    result = {"frontier": [{"x": 10, "y": 20}], "selected": 2}

    await repo.create(
        portfolio_id=portfolio_id,
        workspace_id=ws.workspace_id,
        model_version_id=mv.model_version_id,
        optimization_version="1.0.0",
        config_json=config_json,
        config_hash="sha256:deadbeef",
        objective_metric="gdp",
        cost_metric="cost_sar",
        budget=1_000_000.0,
        min_selected=1,
        max_selected=5,
        candidate_run_ids_json=candidate_ids,
        selected_run_ids_json=selected_ids,
        result_json=result,
        result_checksum="sha256:result123",
    )

    fetched = await repo.get(portfolio_id)
    assert fetched is not None
    assert fetched.portfolio_id == portfolio_id
    assert fetched.workspace_id == ws.workspace_id
    assert fetched.model_version_id == mv.model_version_id
    assert fetched.optimization_version == "1.0.0"
    assert fetched.config_hash == "sha256:deadbeef"
    assert fetched.objective_metric == "gdp"
    assert fetched.cost_metric == "cost_sar"
    assert fetched.budget == pytest.approx(1_000_000.0)
    assert fetched.min_selected == 1
    assert fetched.max_selected == 5
    assert fetched.result_checksum == "sha256:result123"
    assert fetched.created_at is not None


async def test_get_returns_none_for_missing(db_session):
    """Unknown UUID returns None."""
    repo = PortfolioRepository(db_session)
    result = await repo.get(uuid7())
    assert result is None


async def test_get_for_workspace_hit(db_session):
    """Correct workspace returns the row."""
    ws = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws.workspace_id)
    repo = PortfolioRepository(db_session)

    row = await _create_portfolio(repo, ws.workspace_id, mv.model_version_id)

    result = await repo.get_for_workspace(row.portfolio_id, ws.workspace_id)
    assert result is not None
    assert result.portfolio_id == row.portfolio_id


async def test_get_for_workspace_wrong_workspace(db_session):
    """Wrong workspace_id returns None."""
    ws_a = await _seed_workspace(db_session)
    ws_b = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws_a.workspace_id)
    repo = PortfolioRepository(db_session)

    row = await _create_portfolio(repo, ws_a.workspace_id, mv.model_version_id)

    result = await repo.get_for_workspace(row.portfolio_id, ws_b.workspace_id)
    assert result is None


async def test_get_by_config_for_workspace_hit(db_session):
    """Exact match on (workspace_id, config_hash) returns the row."""
    ws = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws.workspace_id)
    repo = PortfolioRepository(db_session)

    row = await _create_portfolio(
        repo,
        ws.workspace_id,
        mv.model_version_id,
        config_hash="sha256:unique_config",
    )

    result = await repo.get_by_config_for_workspace(
        ws.workspace_id,
        "sha256:unique_config",
    )
    assert result is not None
    assert result.portfolio_id == row.portfolio_id


async def test_get_by_config_for_workspace_miss(db_session):
    """Wrong config_hash returns None."""
    ws = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws.workspace_id)
    repo = PortfolioRepository(db_session)

    await _create_portfolio(
        repo,
        ws.workspace_id,
        mv.model_version_id,
        config_hash="sha256:actual_config",
    )

    result = await repo.get_by_config_for_workspace(
        ws.workspace_id,
        "sha256:wrong_config",
    )
    assert result is None


async def test_list_for_workspace_multiple(db_session):
    """Two results, verify order (created_at DESC)."""
    ws = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws.workspace_id)
    repo = PortfolioRepository(db_session)

    row1 = await _create_portfolio(
        repo,
        ws.workspace_id,
        mv.model_version_id,
        config_hash="sha256:config_a",
    )
    row2 = await _create_portfolio(
        repo,
        ws.workspace_id,
        mv.model_version_id,
        config_hash="sha256:config_b",
    )

    rows, total = await repo.list_for_workspace(ws.workspace_id)
    assert total == 2
    assert len(rows) == 2
    # Ordered by created_at DESC — row2 was created after row1
    assert rows[0].portfolio_id == row2.portfolio_id
    assert rows[1].portfolio_id == row1.portfolio_id


async def test_list_for_workspace_pagination(db_session):
    """Create 5, paginate with limit=2."""
    ws = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws.workspace_id)
    repo = PortfolioRepository(db_session)

    for i in range(5):
        await _create_portfolio(
            repo,
            ws.workspace_id,
            mv.model_version_id,
            config_hash=f"sha256:config_{i:03d}",
        )

    page1, total1 = await repo.list_for_workspace(
        ws.workspace_id,
        limit=2,
        offset=0,
    )
    assert total1 == 5
    assert len(page1) == 2

    page2, total2 = await repo.list_for_workspace(
        ws.workspace_id,
        limit=2,
        offset=2,
    )
    assert total2 == 5
    assert len(page2) == 2

    page3, total3 = await repo.list_for_workspace(
        ws.workspace_id,
        limit=2,
        offset=4,
    )
    assert total3 == 5
    assert len(page3) == 1

    # No overlap between pages
    all_ids = [r.portfolio_id for r in page1 + page2 + page3]
    assert len(set(all_ids)) == 5


async def test_list_for_workspace_isolation(db_session):
    """Cross-workspace returns empty."""
    ws_a = await _seed_workspace(db_session)
    ws_b = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws_a.workspace_id)
    repo = PortfolioRepository(db_session)

    await _create_portfolio(
        repo,
        ws_a.workspace_id,
        mv.model_version_id,
        config_hash="sha256:config_a_only",
    )

    rows_a, total_a = await repo.list_for_workspace(ws_a.workspace_id)
    assert total_a == 1
    assert rows_a[0].workspace_id == ws_a.workspace_id

    rows_b, total_b = await repo.list_for_workspace(ws_b.workspace_id)
    assert total_b == 0
    assert len(rows_b) == 0


async def test_idempotent_config_hash(db_session):
    """Same (workspace_id, config_hash) raises IntegrityError."""
    ws = await _seed_workspace(db_session)
    mv = await _seed_model(db_session, ws.workspace_id)
    repo = PortfolioRepository(db_session)

    await _create_portfolio(
        repo,
        ws.workspace_id,
        mv.model_version_id,
        config_hash="sha256:duplicate",
    )

    with pytest.raises(IntegrityError):
        await repo.create(
            portfolio_id=uuid7(),
            workspace_id=ws.workspace_id,
            model_version_id=mv.model_version_id,
            optimization_version="1.0.0",
            config_json={"objective": "gdp"},
            config_hash="sha256:duplicate",
            objective_metric="gdp",
            cost_metric="cost_sar",
            budget=100_000.0,
            min_selected=1,
            max_selected=5,
            candidate_run_ids_json=[],
            selected_run_ids_json=[],
            result_json={},
            result_checksum="sha256:different_result",
        )
