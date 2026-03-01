"""Tests for G2: deterministic compile from stored document data.

Currently compile_scenario in scenarios.py requires line_items in the
CompileRequest body. These tests verify the new document_id-based compile
flow where the route fetches extracted line items from the database instead
of requiring them inline.

These tests will FAIL because:
1. CompileRequest requires line_items (not optional), so sending document_id
   without line_items returns 422.
2. No deprecation header is added for legacy payload compiles.
"""

import csv
import io

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


def _make_csv_content() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows([
        ["Description", "Quantity", "Unit", "Unit Price", "Total"],
        ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
        ["Concrete Works", "20000", "m3", "450", "9000000"],
    ])
    return buf.getvalue().encode("utf-8")


async def _upload_and_extract(
    client: AsyncClient, workspace_id: str,
) -> tuple[str, str]:
    """Upload CSV document and trigger extraction. Returns (doc_id, job_id)."""
    uploaded_by = str(uuid7())
    upload_resp = await client.post(
        f"/v1/workspaces/{workspace_id}/documents",
        files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
        data={
            "doc_type": "BOQ",
            "source_type": "CLIENT",
            "classification": "RESTRICTED",
            "language": "en",
            "uploaded_by": uploaded_by,
        },
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["doc_id"]

    extract_resp = await client.post(
        f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
        json={"extract_tables": True, "extract_line_items": True},
    )
    assert extract_resp.status_code == 202
    job_id = extract_resp.json()["job_id"]

    return doc_id, job_id


async def _create_scenario(
    client: AsyncClient, workspace_id: str,
) -> str:
    """Create a scenario and return its scenario_spec_id."""
    scenario_resp = await client.post(
        f"/v1/workspaces/{workspace_id}/scenarios",
        json={
            "name": "Test Scenario",
            "base_model_version_id": str(uuid7()),
            "base_year": 2023,
            "start_year": 2023,
            "end_year": 2030,
        },
    )
    assert scenario_resp.status_code == 201
    return scenario_resp.json()["scenario_spec_id"]


class TestCompileFromDocument:
    """G2: Compile should accept document_id instead of inline line_items."""

    @pytest.mark.anyio
    async def test_compile_from_stored_document(self, client: AsyncClient) -> None:
        """Upload CSV, extract, create scenario, compile with document_id.

        Should return 200 with shock_items derived from stored extraction data.
        Currently FAILS because CompileRequest doesn't accept document_id.
        """
        workspace_id = str(uuid7())
        doc_id, _job_id = await _upload_and_extract(client, workspace_id)
        scenario_id = await _create_scenario(client, workspace_id)

        # Compile using document_id (new flow)
        compile_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile",
            json={
                "document_id": doc_id,
                "decisions": [],
                "phasing": {"2023": 0.3, "2024": 0.4, "2025": 0.3},
                "default_domestic_share": 0.65,
            },
        )

        assert compile_resp.status_code == 200
        data = compile_resp.json()
        assert "shock_items" in data
        assert len(data["shock_items"]) >= 1

    @pytest.mark.anyio
    async def test_compile_rejects_doc_without_extraction(
        self, client: AsyncClient,
    ) -> None:
        """Upload but DON'T extract, compile with document_id -> 409.

        The route should check that extraction has completed and reject
        documents that have no extracted line items.
        """
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())

        # Upload only (no extraction)
        upload_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["doc_id"]

        scenario_id = await _create_scenario(client, workspace_id)

        # Compile using document_id without extraction
        compile_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile",
            json={
                "document_id": doc_id,
                "decisions": [],
                "phasing": {"2023": 1.0},
                "default_domestic_share": 0.65,
            },
        )

        assert compile_resp.status_code == 409

    @pytest.mark.anyio
    async def test_payload_compile_returns_deprecation_header(
        self, client: AsyncClient,
    ) -> None:
        """Legacy payload compile should return 200 with a deprecation header.

        The old flow with inline line_items should still work but the response
        should include a "deprecation" header signaling clients to migrate
        to document_id-based compile.
        """
        workspace_id = str(uuid7())
        scenario_id = await _create_scenario(client, workspace_id)

        line_item_id = str(uuid7())
        decided_by = str(uuid7())

        compile_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile",
            json={
                "line_items": [
                    {
                        "line_item_id": line_item_id,
                        "description": "Structural Steel",
                        "total_value": 17500000.0,
                        "currency_code": "SAR",
                    },
                ],
                "decisions": [
                    {
                        "line_item_id": line_item_id,
                        "final_sector_code": "C41",
                        "decision_type": "APPROVED",
                        "suggested_confidence": 0.95,
                        "decided_by": decided_by,
                    },
                ],
                "phasing": {"2023": 0.3, "2024": 0.4, "2025": 0.3},
                "default_domestic_share": 0.65,
            },
        )

        assert compile_resp.status_code == 200

        # Check for deprecation header (case-insensitive)
        deprecation_header = compile_resp.headers.get("deprecation")
        assert deprecation_header is not None, (
            "Legacy payload compile should return a 'deprecation' header. "
            f"Headers received: {dict(compile_resp.headers)}"
        )
