"""Tests for B-11 claim list/detail/update endpoints.

Covers:
- GET  /{ws}/governance/claims          — list claims (filtered by run_id)
- GET  /{ws}/governance/claims/{id}     — claim detail
- PATCH /{ws}/governance/claims/{id}    — update claim status with transition validation

Note: The ClaimExtractor auto-classifies claim types heuristically:
  - MODEL / SOURCE_FACT types start with status NEEDS_EVIDENCE
  - ASSUMPTION / RECOMMENDATION types start with status EXTRACTED
Tests use appropriate draft text to get the desired initial status.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = str(uuid7())

# Draft texts that produce claims in known initial states:
#   "We assume ..." => ASSUMPTION type => status EXTRACTED
#   "Total GDP ..." => MODEL type => status NEEDS_EVIDENCE
_ASSUMPTION_TEXT = "We assume 65% domestic share."
_MODEL_TEXT = "Total GDP impact is SAR 4.2 billion."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _extract_claims(client: AsyncClient, draft_text: str, run_id: str | None = None) -> dict:
    """Extract claims via the existing endpoint and return the response JSON."""
    rid = run_id or str(uuid7())
    resp = await client.post(
        f"/v1/workspaces/{WS_ID}/governance/claims/extract",
        json={"draft_text": draft_text, "run_id": rid},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# TestClaimList
# ---------------------------------------------------------------------------


class TestClaimList:
    @pytest.mark.anyio
    async def test_list_claims_empty(self, client: AsyncClient) -> None:
        """A run_id with no claims returns 200, empty items, total=0."""
        run_id = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims",
            params={"run_id": run_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_list_claims_returns_extracted(self, client: AsyncClient) -> None:
        """Extract claims, then list — finds them."""
        run_id = str(uuid7())
        extract = await _extract_claims(
            client,
            f"{_MODEL_TEXT} {_ASSUMPTION_TEXT}",
            run_id=run_id,
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims",
            params={"run_id": run_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == extract["total"]
        assert len(data["items"]) == extract["total"]
        # Each item should have essential fields
        for item in data["items"]:
            assert "claim_id" in item
            assert "text" in item
            assert "claim_type" in item
            assert "status" in item

    @pytest.mark.anyio
    async def test_list_claims_filters_by_run(self, client: AsyncClient) -> None:
        """Two different run_ids — verify isolation."""
        run_a = str(uuid7())
        run_b = str(uuid7())
        await _extract_claims(client, _MODEL_TEXT, run_id=run_a)
        await _extract_claims(
            client,
            f"{_ASSUMPTION_TEXT} We recommend phased approach.",
            run_id=run_b,
        )
        resp_a = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims",
            params={"run_id": run_a},
        )
        resp_b = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims",
            params={"run_id": run_b},
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        ids_a = {item["claim_id"] for item in resp_a.json()["items"]}
        ids_b = {item["claim_id"] for item in resp_b.json()["items"]}
        assert ids_a.isdisjoint(ids_b), "Claims from different runs must not overlap"


# ---------------------------------------------------------------------------
# TestClaimDetail
# ---------------------------------------------------------------------------


class TestClaimDetail:
    @pytest.mark.anyio
    async def test_detail_returns_claim(self, client: AsyncClient) -> None:
        """Extract, get detail -> 200 with all fields."""
        run_id = str(uuid7())
        extract = await _extract_claims(client, _MODEL_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["claim_id"] == claim_id
        assert "text" in data
        assert "claim_type" in data
        assert "status" in data
        assert "disclosure_tier" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.anyio
    async def test_detail_404_not_found(self, client: AsyncClient) -> None:
        """Fake claim_id -> 404."""
        fake_id = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/claims/{fake_id}",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestClaimUpdate
# ---------------------------------------------------------------------------


class TestClaimUpdate:
    @pytest.mark.anyio
    async def test_valid_transition_extracted_to_needs_evidence(self, client: AsyncClient) -> None:
        """EXTRACTED -> NEEDS_EVIDENCE -> 200.

        Uses ASSUMPTION text which starts in EXTRACTED status.
        """
        run_id = str(uuid7())
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]
        # Verify initial status is EXTRACTED
        assert extract["claims"][0]["status"] == "EXTRACTED"
        resp = await client.patch(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
            json={"status": "NEEDS_EVIDENCE"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "NEEDS_EVIDENCE"
        assert data["claim_id"] == claim_id

    @pytest.mark.anyio
    async def test_invalid_transition_returns_409(self, client: AsyncClient) -> None:
        """EXTRACTED -> APPROVED_FOR_EXPORT -> 409.

        Uses ASSUMPTION text which starts in EXTRACTED status.
        """
        run_id = str(uuid7())
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]
        assert extract["claims"][0]["status"] == "EXTRACTED"
        resp = await client.patch(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
            json={"status": "APPROVED_FOR_EXPORT"},
        )
        assert resp.status_code == 409
        assert "EXTRACTED" in resp.json()["detail"]
        assert "APPROVED_FOR_EXPORT" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_update_nonexistent_claim_404(self, client: AsyncClient) -> None:
        """Fake claim_id -> 404."""
        fake_id = str(uuid7())
        resp = await client.patch(
            f"/v1/workspaces/{WS_ID}/governance/claims/{fake_id}",
            json={"status": "NEEDS_EVIDENCE"},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_multi_step_transition(self, client: AsyncClient) -> None:
        """EXTRACTED -> NEEDS_EVIDENCE -> SUPPORTED -> APPROVED_FOR_EXPORT all 200.

        Uses ASSUMPTION text which starts in EXTRACTED status.
        """
        run_id = str(uuid7())
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]
        assert extract["claims"][0]["status"] == "EXTRACTED"

        steps = ["NEEDS_EVIDENCE", "SUPPORTED", "APPROVED_FOR_EXPORT"]
        for target_status in steps:
            resp = await client.patch(
                f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
                json={"status": target_status},
            )
            assert resp.status_code == 200, f"Failed transition to {target_status}"
            assert resp.json()["status"] == target_status

    @pytest.mark.anyio
    async def test_transition_from_terminal_state_409(self, client: AsyncClient) -> None:
        """DELETED -> anything -> 409.

        Uses ASSUMPTION text which starts in EXTRACTED status.
        """
        run_id = str(uuid7())
        extract = await _extract_claims(client, _ASSUMPTION_TEXT, run_id=run_id)
        claim_id = extract["claims"][0]["claim_id"]

        # First transition to DELETED (valid from EXTRACTED)
        resp = await client.patch(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
            json={"status": "DELETED"},
        )
        assert resp.status_code == 200

        # Now try to transition from DELETED (terminal state)
        resp = await client.patch(
            f"/v1/workspaces/{WS_ID}/governance/claims/{claim_id}",
            json={"status": "NEEDS_EVIDENCE"},
        )
        assert resp.status_code == 409
