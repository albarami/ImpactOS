"""Tests for workshop session API endpoints -- Sprint 22.

Tests session CRUD, idempotency, workspace isolation, and export gate.
Preview and commit endpoints are integration-heavy (require in-memory ModelStore)
and are deferred to integration testing.
"""

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from uuid_extensions import uuid7

from src.db.session import get_async_session
from src.db.tables import (
    ModelDataRow,
    ModelVersionRow,
    RunSnapshotRow,
    WorkspaceRow,
)
from src.engine.model_store import compute_model_checksum
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS_ID = uuid7()
OTHER_WS_ID = uuid7()

SECTOR_CODES = ["A", "B", "C"]
N = len(SECTOR_CODES)
Z_MATRIX = np.eye(N, dtype=np.float64) * 0.1
X_VECTOR = np.ones(N, dtype=np.float64) * 100.0

BASE_SHOCKS = {"2024": [1.0, 2.0, 3.0], "2025": [1.5, 2.5, 3.5]}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_workspace(session, workspace_id):
    ws = WorkspaceRow(
        workspace_id=workspace_id,
        client_name="Test",
        engagement_code="T-001",
        classification="INTERNAL",
        description="test",
        created_by=uuid7(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(ws)
    await session.flush()
    return ws


async def _seed_model(session):
    mid = uuid7()
    checksum = compute_model_checksum(Z_MATRIX, X_VECTOR, {})
    mv = ModelVersionRow(
        model_version_id=mid,
        base_year=2023,
        source="test",
        sector_count=N,
        checksum=checksum,
        provenance_class="curated_real",
        created_at=utc_now(),
    )
    session.add(mv)
    md = ModelDataRow(
        model_version_id=mid,
        z_matrix_json=Z_MATRIX.tolist(),
        x_vector_json=X_VECTOR.tolist(),
        sector_codes=SECTOR_CODES,
        storage_format="json",
    )
    session.add(md)
    await session.flush()
    return mid


async def _seed_run(session, model_version_id, workspace_id):
    run_id = uuid7()
    snap = RunSnapshotRow(
        run_id=run_id,
        model_version_id=model_version_id,
        taxonomy_version_id=uuid7(),
        concordance_version_id=uuid7(),
        mapping_library_version_id=uuid7(),
        assumption_library_version_id=uuid7(),
        prompt_pack_version_id=uuid7(),
        workspace_id=workspace_id,
        source_checksums=[],
        created_at=utc_now(),
    )
    session.add(snap)
    await session.flush()
    return run_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded(db_session):
    """Seed workspace, model, baseline run."""
    await _seed_workspace(db_session, WS_ID)
    model_id = await _seed_model(db_session)
    run_id = await _seed_run(db_session, model_id, WS_ID)
    return {"model_id": model_id, "run_id": run_id}


@pytest.fixture
async def seeded_two_workspaces(db_session):
    """Seed two workspaces with separate runs for isolation tests."""
    await _seed_workspace(db_session, WS_ID)
    await _seed_workspace(db_session, OTHER_WS_ID)
    model_id = await _seed_model(db_session)
    run_id = await _seed_run(db_session, model_id, WS_ID)
    other_run_id = await _seed_run(db_session, model_id, OTHER_WS_ID)
    return {
        "model_id": model_id,
        "run_id": run_id,
        "other_run_id": other_run_id,
    }


@pytest.fixture
async def ws_client(db_session):
    """AsyncClient with session + auth overrides for workshop tests."""
    from src.api.auth_deps import (
        AuthPrincipal,
        WorkspaceMember,
        get_current_principal,
        require_workspace_member,
    )
    from src.api.main import app

    _principal = AuthPrincipal(
        user_id=uuid7(),
        username="workshop-tester",
        role="admin",
    )

    async def _override_session():
        yield db_session

    async def _override_principal():
        return _principal

    async def _override_workspace_member(workspace_id=None):
        return WorkspaceMember(
            principal=_principal,
            workspace_id=workspace_id or WS_ID,
            role="admin",
        )

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_current_principal] = _override_principal
    app.dependency_overrides[require_workspace_member] = _override_workspace_member

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def _make_create_payload(run_id, **overrides):
    """Build a valid POST payload for creating a workshop session."""
    base = {
        "baseline_run_id": str(run_id),
        "base_shocks": BASE_SHOCKS,
        "sliders": [
            {"sector_code": "A", "pct_delta": 10.0},
            {"sector_code": "B", "pct_delta": -5.0},
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestCreateWorkshopSession
# ---------------------------------------------------------------------------


class TestCreateWorkshopSession:
    """Tests for POST /{workspace_id}/workshop/sessions."""

    async def test_create_session_201(self, ws_client, seeded, db_session):
        """Happy path -- POST creates workshop session and returns 201."""
        payload = _make_create_payload(seeded["run_id"])
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "session_id" in body
        assert body["workspace_id"] == str(WS_ID)
        assert body["baseline_run_id"] == str(seeded["run_id"])
        assert body["status"] == "draft"
        assert body["committed_run_id"] is None
        assert len(body["slider_config"]) == 2
        assert body["slider_config"][0]["sector_code"] == "A"
        assert body["slider_config"][0]["pct_delta"] == 10.0
        assert "config_hash" in body
        assert "created_at" in body
        assert "updated_at" in body

    async def test_create_idempotent_200(self, ws_client, seeded, db_session):
        """Second POST with same config returns 200 with same session_id."""
        payload = _make_create_payload(seeded["run_id"])
        r1 = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert r1.status_code == 201
        sid1 = r1.json()["session_id"]

        r2 = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert r2.status_code == 200
        assert r2.json()["session_id"] == sid1

    async def test_create_invalid_baseline_422(self, ws_client, seeded, db_session):
        """Nonexistent baseline_run_id -> 422 WORKSHOP_NO_BASELINE."""
        payload = _make_create_payload(uuid7())
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_NO_BASELINE"

    async def test_create_unknown_sector_422(self, ws_client, seeded, db_session):
        """Slider with invalid sector -> 422 WORKSHOP_UNKNOWN_SECTOR."""
        payload = _make_create_payload(
            seeded["run_id"],
            sliders=[{"sector_code": "INVALID_SECTOR", "pct_delta": 5.0}],
        )
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_UNKNOWN_SECTOR"

    async def test_create_duplicate_sector_422(self, ws_client, seeded, db_session):
        """Duplicate sector in sliders -> 422 WORKSHOP_DUPLICATE_SECTOR."""
        payload = _make_create_payload(
            seeded["run_id"],
            sliders=[
                {"sector_code": "A", "pct_delta": 10.0},
                {"sector_code": "A", "pct_delta": 20.0},
            ],
        )
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_DUPLICATE_SECTOR"

    async def test_create_bad_base_shocks_length_422(self, ws_client, seeded, db_session):
        """Wrong array length in base_shocks -> 422 WORKSHOP_INVALID_CONFIG."""
        payload = _make_create_payload(
            seeded["run_id"],
            base_shocks={"2024": [1.0, 2.0]},  # only 2, model has 3 sectors
        )
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_INVALID_CONFIG"

    async def test_create_empty_base_shocks_422(self, ws_client, seeded, db_session):
        """Empty base_shocks dict -> 422 WORKSHOP_INVALID_CONFIG."""
        payload = _make_create_payload(
            seeded["run_id"],
            base_shocks={},
        )
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_INVALID_CONFIG"


# ---------------------------------------------------------------------------
# TestGetWorkshopSession
# ---------------------------------------------------------------------------


class TestGetWorkshopSession:
    """Tests for GET /{workspace_id}/workshop/sessions/{session_id}."""

    async def test_get_session_200(self, ws_client, seeded, db_session):
        """Create then GET returns 200 with matching data."""
        payload = _make_create_payload(seeded["run_id"])
        r1 = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert r1.status_code == 201
        sid = r1.json()["session_id"]

        r2 = await ws_client.get(
            f"/v1/workspaces/{WS_ID}/workshop/sessions/{sid}",
        )
        assert r2.status_code == 200
        assert r2.json()["session_id"] == sid
        assert r2.json()["status"] == "draft"

    async def test_get_nonexistent_404(self, ws_client, seeded, db_session):
        """Nonexistent session_id -> 404 WORKSHOP_SESSION_NOT_FOUND."""
        fake_id = uuid7()
        resp = await ws_client.get(
            f"/v1/workspaces/{WS_ID}/workshop/sessions/{fake_id}",
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_SESSION_NOT_FOUND"

    async def test_get_wrong_workspace_404(self, ws_client, seeded_two_workspaces, db_session):
        """Session in workspace A not visible from workspace B -> 404."""
        payload = _make_create_payload(seeded_two_workspaces["run_id"])
        r1 = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert r1.status_code == 201
        sid = r1.json()["session_id"]

        # Try to GET from OTHER_WS_ID
        resp = await ws_client.get(
            f"/v1/workspaces/{OTHER_WS_ID}/workshop/sessions/{sid}",
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_SESSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# TestListWorkshopSessions
# ---------------------------------------------------------------------------


class TestListWorkshopSessions:
    """Tests for GET /{workspace_id}/workshop/sessions."""

    async def test_list_empty(self, ws_client, seeded, db_session):
        """Empty workspace returns empty list."""
        resp = await ws_client.get(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    async def test_list_pagination(self, ws_client, seeded, db_session):
        """3 sessions, limit=2 returns 2 items with total=3."""
        for i in range(3):
            payload = _make_create_payload(
                seeded["run_id"],
                sliders=[{"sector_code": "A", "pct_delta": float(i + 1) * 10}],
            )
            r = await ws_client.post(
                f"/v1/workspaces/{WS_ID}/workshop/sessions",
                json=payload,
            )
            assert r.status_code == 201, r.text

        resp = await ws_client.get(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            params={"limit": 2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2


# ---------------------------------------------------------------------------
# TestExportWorkshopSession
# ---------------------------------------------------------------------------


class TestExportWorkshopSession:
    """Tests for POST /{workspace_id}/workshop/sessions/{session_id}/export."""

    async def test_export_uncommitted_422(self, ws_client, seeded, db_session):
        """Draft session -> 422 WORKSHOP_NOT_COMMITTED."""
        payload = _make_create_payload(seeded["run_id"])
        r1 = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions",
            json=payload,
        )
        assert r1.status_code == 201
        sid = r1.json()["session_id"]

        export_payload = {
            "mode": "decision_pack",
            "export_formats": ["pdf"],
            "pack_data": {},
        }
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions/{sid}/export",
            json=export_payload,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_NOT_COMMITTED"

    async def test_export_nonexistent_404(self, ws_client, seeded, db_session):
        """Nonexistent session_id -> 404 WORKSHOP_SESSION_NOT_FOUND."""
        fake_id = uuid7()
        export_payload = {
            "mode": "decision_pack",
            "export_formats": ["pdf"],
            "pack_data": {},
        }
        resp = await ws_client.post(
            f"/v1/workspaces/{WS_ID}/workshop/sessions/{fake_id}/export",
            json=export_payload,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["reason_code"] == "WORKSHOP_SESSION_NOT_FOUND"
