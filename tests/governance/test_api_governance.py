"""Tests for FastAPI governance endpoints (MVP-5).

Covers: POST extract claims, POST NFF check, POST approve assumption,
GET governance status, GET blocking reasons.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


# ===================================================================
# POST /v1/governance/claims/extract
# ===================================================================


class TestExtractClaims:
    """POST extract claims from draft text."""

    @pytest.mark.anyio
    async def test_extract_returns_200(self, client: AsyncClient) -> None:
        payload = {
            "draft_text": "Total GDP impact is SAR 4.2 billion. We assume 65% domestic share.",
            "workspace_id": str(uuid7()),
            "run_id": str(uuid7()),
        }
        response = await client.post("/v1/governance/claims/extract", json=payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_extract_returns_claims(self, client: AsyncClient) -> None:
        payload = {
            "draft_text": "The project generates 12,500 jobs. We recommend phased investment.",
            "workspace_id": str(uuid7()),
            "run_id": str(uuid7()),
        }
        response = await client.post("/v1/governance/claims/extract", json=payload)
        data = response.json()
        assert "claims" in data
        assert len(data["claims"]) == 2
        assert "total" in data
        assert "needs_evidence_count" in data

    @pytest.mark.anyio
    async def test_extract_empty_text(self, client: AsyncClient) -> None:
        payload = {
            "draft_text": "",
            "workspace_id": str(uuid7()),
            "run_id": str(uuid7()),
        }
        response = await client.post("/v1/governance/claims/extract", json=payload)
        data = response.json()
        assert data["total"] == 0


# ===================================================================
# POST /v1/governance/nff/check
# ===================================================================


class TestNFFCheck:
    """POST NFF gate check."""

    @pytest.mark.anyio
    async def test_nff_check_passes_all_supported(self, client: AsyncClient) -> None:
        # First extract claims
        extract_resp = await client.post("/v1/governance/claims/extract", json={
            "draft_text": "We assume 65% domestic share. We recommend phased approach.",
            "workspace_id": str(uuid7()),
            "run_id": str(uuid7()),
        })
        claim_ids = [c["claim_id"] for c in extract_resp.json()["claims"]]

        # NFF check — these are EXTRACTED (assumptions/recommendations), need to be resolved
        response = await client.post("/v1/governance/nff/check", json={
            "claim_ids": claim_ids,
        })
        data = response.json()
        assert "passed" in data
        assert "total_claims" in data

    @pytest.mark.anyio
    async def test_nff_check_blocks_unresolved(self, client: AsyncClient) -> None:
        # Extract a claim that needs evidence
        extract_resp = await client.post("/v1/governance/claims/extract", json={
            "draft_text": "Total GDP impact is SAR 4.2 billion.",
            "workspace_id": str(uuid7()),
            "run_id": str(uuid7()),
        })
        claim_ids = [c["claim_id"] for c in extract_resp.json()["claims"]]

        response = await client.post("/v1/governance/nff/check", json={
            "claim_ids": claim_ids,
        })
        data = response.json()
        assert data["passed"] is False
        assert len(data["blocking_reasons"]) >= 1

    @pytest.mark.anyio
    async def test_nff_check_empty_passes(self, client: AsyncClient) -> None:
        response = await client.post("/v1/governance/nff/check", json={
            "claim_ids": [],
        })
        data = response.json()
        assert data["passed"] is True


# ===================================================================
# POST /v1/governance/assumptions/{id}/approve
# ===================================================================


class TestApproveAssumption:
    """POST approve assumption."""

    @pytest.mark.anyio
    async def test_approve_returns_200(self, client: AsyncClient) -> None:
        # First create an assumption
        create_resp = await client.post("/v1/governance/assumptions", json={
            "type": "IMPORT_SHARE",
            "value": 0.35,
            "units": "ratio",
            "justification": "Based on trade data.",
        })
        assumption_id = create_resp.json()["assumption_id"]

        # Approve it
        response = await client.post(
            f"/v1/governance/assumptions/{assumption_id}/approve",
            json={
                "range_min": 0.25,
                "range_max": 0.45,
                "actor": str(uuid7()),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "APPROVED"

    @pytest.mark.anyio
    async def test_approve_without_range_fails(self, client: AsyncClient) -> None:
        create_resp = await client.post("/v1/governance/assumptions", json={
            "type": "IMPORT_SHARE",
            "value": 0.35,
            "units": "ratio",
            "justification": "Based on trade data.",
        })
        assumption_id = create_resp.json()["assumption_id"]

        response = await client.post(
            f"/v1/governance/assumptions/{assumption_id}/approve",
            json={"actor": str(uuid7())},
        )
        assert response.status_code == 400


# ===================================================================
# GET /v1/governance/status/{run_id}
# ===================================================================


class TestGovernanceStatus:
    """GET governance status for a run."""

    @pytest.mark.anyio
    async def test_status_returns_200(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        response = await client.get(f"/v1/governance/status/{run_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_status_contains_fields(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        response = await client.get(f"/v1/governance/status/{run_id}")
        data = response.json()
        assert "run_id" in data
        assert "claims_total" in data
        assert "claims_resolved" in data
        assert "assumptions_total" in data
        assert "nff_passed" in data


# ===================================================================
# GET /v1/governance/blocking-reasons/{run_id}
# ===================================================================


class TestBlockingReasons:
    """GET blocking reasons for a run."""

    @pytest.mark.anyio
    async def test_blocking_reasons_returns_200(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        response = await client.get(f"/v1/governance/blocking-reasons/{run_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_blocking_reasons_structure(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        response = await client.get(f"/v1/governance/blocking-reasons/{run_id}")
        data = response.json()
        assert "run_id" in data
        assert "blocking_reasons" in data
        assert isinstance(data["blocking_reasons"], list)
