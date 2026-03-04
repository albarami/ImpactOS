"""Tests for POST /{workspace_id}/models/import-sg endpoint.

Sprint 18: SG model import with fail-closed parity gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

pytestmark = pytest.mark.anyio

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SG_XLSX = FIXTURE_DIR / "sg_3sector_model.xlsx"
BENCHMARK_JSON = FIXTURE_DIR / "sg_parity_benchmark_v1.json"


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


def _load_benchmark() -> dict:
    """Load the golden benchmark from fixtures."""
    with open(BENCHMARK_JSON) as f:
        return json.load(f)


def _corrupted_benchmark() -> dict:
    """Return a benchmark with wrong expected values to force parity failure."""
    bm = _load_benchmark()
    bm["expected_outputs"]["total_output"] = 999999.0
    bm["expected_outputs"]["employment"] = 888888.0
    return bm


class TestImportHappyPath:
    async def test_import_happy_path(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Upload fixture xlsx, get 200 with verified parity."""
        with open(SG_XLSX, "rb") as f:
            resp = await client.post(
                f"/v1/workspaces/{workspace_id}/models/import-sg",
                files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "model_version_id" in data
        assert data["sector_count"] == 3
        assert data["checksum"].startswith("sha256:")
        assert data["provenance_class"] == "curated_real"
        assert data["parity_status"] == "verified"

    async def test_import_sg_provenance_populated(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Response has sg_provenance with import_mode, workbook_sha256, parity fields."""
        with open(SG_XLSX, "rb") as f:
            resp = await client.post(
                f"/v1/workspaces/{workspace_id}/models/import-sg",
                files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
            )
        assert resp.status_code == 200, resp.text
        prov = resp.json()["sg_provenance"]
        assert prov["import_mode"] == "sg_workbook"
        assert prov["workbook_sha256"].startswith("sha256:")
        assert prov["parity_status"] == "verified"
        assert prov["dev_bypass"] is False
        assert "source_filename" in prov


class TestParityFailure:
    async def test_parity_failure_returns_422(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Corrupted benchmark -> parity failure -> 422 with reason_code and metrics."""
        with patch(
            "src.api.models._load_parity_benchmark",
            return_value=_corrupted_benchmark(),
        ):
            with open(SG_XLSX, "rb") as f:
                resp = await client.post(
                    f"/v1/workspaces/{workspace_id}/models/import-sg",
                    files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
                )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "PARITY_TOLERANCE_BREACH"
        assert "metrics" in detail
        assert len(detail["metrics"]) > 0
        for m in detail["metrics"]:
            assert "metric" in m
            assert "expected" in m
            assert "actual" in m
            assert "error_pct" in m
            assert "passed" in m

    async def test_parity_failure_rollback_no_model_row(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """CRITICAL: after parity failure 422, GET /versions returns 0 models."""
        with patch(
            "src.api.models._load_parity_benchmark",
            return_value=_corrupted_benchmark(),
        ):
            with open(SG_XLSX, "rb") as f:
                resp = await client.post(
                    f"/v1/workspaces/{workspace_id}/models/import-sg",
                    files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
                )
        assert resp.status_code == 422

        list_resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions",
        )
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 0


class TestDevBypass:
    async def test_dev_bypass_in_dev_env(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """In DEV env with parity failure + dev_bypass=True -> 200, bypassed."""
        with patch(
            "src.api.models._load_parity_benchmark",
            return_value=_corrupted_benchmark(),
        ), patch(
            "src.api.models._is_dev_bypass_allowed",
            return_value=True,
        ):
            with open(SG_XLSX, "rb") as f:
                resp = await client.post(
                    f"/v1/workspaces/{workspace_id}/models/import-sg",
                    files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
                    params={"dev_bypass": "true"},
                )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["parity_status"] == "bypassed"
        assert data["provenance_class"] == "curated_estimated"
        assert data["sg_provenance"]["dev_bypass"] is True

    async def test_dev_bypass_rejected_in_prod(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """In PROD env with parity failure + dev_bypass=True -> still 422."""
        with patch(
            "src.api.models._load_parity_benchmark",
            return_value=_corrupted_benchmark(),
        ), patch(
            "src.api.models._is_dev_bypass_allowed",
            return_value=False,
        ):
            with open(SG_XLSX, "rb") as f:
                resp = await client.post(
                    f"/v1/workspaces/{workspace_id}/models/import-sg",
                    files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
                    params={"dev_bypass": "true"},
                )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "PARITY_TOLERANCE_BREACH"


class TestUnsupportedFormat:
    async def test_unsupported_format_422(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Upload .csv file -> 422 with SG_UNSUPPORTED_FORMAT."""
        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/models/import-sg",
            files={"workbook": ("data.csv", b"a,b,c\n1,2,3\n", "text/csv")},
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "SG_UNSUPPORTED_FORMAT"
        assert ".csv" in detail["message"]


class TestModelVisibility:
    async def test_model_visible_after_import(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """After successful import, GET /versions lists the model."""
        with open(SG_XLSX, "rb") as f:
            import_resp = await client.post(
                f"/v1/workspaces/{workspace_id}/models/import-sg",
                files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
            )
        assert import_resp.status_code == 200
        mv_id = import_resp.json()["model_version_id"]

        list_resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions",
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] >= 1
        ids = [item["model_version_id"] for item in data["items"]]
        assert mv_id in ids

    async def test_sg_provenance_in_get_response(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """After import, GET /versions/{id} includes sg_provenance."""
        with open(SG_XLSX, "rb") as f:
            import_resp = await client.post(
                f"/v1/workspaces/{workspace_id}/models/import-sg",
                files={"workbook": ("sg_3sector_model.xlsx", f, "application/octet-stream")},
            )
        assert import_resp.status_code == 200
        mv_id = import_resp.json()["model_version_id"]

        get_resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["sg_provenance"] is not None
        assert data["sg_provenance"]["import_mode"] == "sg_workbook"
        assert data["sg_provenance"]["parity_status"] == "verified"
