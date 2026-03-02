"""Tests for B-4, B-5, B-8: Mapping decision CRUD, bulk approve, audit trail.

All endpoints are compiler-scoped:
  GET  /v1/workspaces/{ws}/compiler/{cid}/decisions/{li}          — B-4 get
  PUT  /v1/workspaces/{ws}/compiler/{cid}/decisions/{li}          — B-4 put
  POST /v1/workspaces/{ws}/compiler/{cid}/decisions/bulk-approve  — B-5
  GET  /v1/workspaces/{ws}/compiler/{cid}/decisions/{li}/audit    — B-8
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


@pytest.fixture
def other_workspace_id() -> str:
    return str(uuid7())


async def _trigger_compilation(
    client: AsyncClient,
    workspace_id: str,
) -> str:
    """Trigger a compilation via POST and return compilation_id."""
    resp = await client.post(
        f"/v1/workspaces/{workspace_id}/compiler/compile",
        json={
            "scenario_name": "Decision Test Scenario",
            "base_model_version_id": str(uuid7()),
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2028,
            "line_items": [
                {
                    "line_item_id": str(uuid7()),
                    "raw_text": "concrete works for building foundation",
                    "total_value": 500000.0,
                },
                {
                    "line_item_id": str(uuid7()),
                    "raw_text": "transport services for materials",
                    "total_value": 100000.0,
                },
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["compilation_id"]


async def _create_decision(
    client: AsyncClient,
    workspace_id: str,
    compilation_id: str,
    line_item_id: str,
    *,
    state: str = "AI_SUGGESTED",
    suggested_sector_code: str = "F",
    suggested_confidence: float = 0.92,
    final_sector_code: str | None = None,
    decision_type: str = "APPROVED",
    decision_note: str = "Test decision",
    decided_by: str | None = None,
) -> dict:
    """Create a mapping decision via PUT and return the response body."""
    resp = await client.put(
        f"/v1/workspaces/{workspace_id}/compiler/{compilation_id}"
        f"/decisions/{line_item_id}",
        json={
            "state": state,
            "suggested_sector_code": suggested_sector_code,
            "suggested_confidence": suggested_confidence,
            "final_sector_code": final_sector_code or suggested_sector_code,
            "decision_type": decision_type,
            "decision_note": decision_note,
            "decided_by": decided_by or str(uuid7()),
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# =========================================================================
# B-4: Per-line mapping decision CRUD
# =========================================================================


class TestDecisionGet:
    """B-4: GET /v1/workspaces/{ws}/compiler/{cid}/decisions/{line_item_id}"""

    @pytest.mark.anyio
    async def test_get_existing_decision(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        await _create_decision(client, workspace_id, cid, li_id)

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["line_item_id"] == li_id
        assert data["compilation_id"] == cid
        assert data["state"] == "AI_SUGGESTED"
        assert data["suggested_sector_code"] == "F"
        assert "decided_at" in data
        assert "created_at" in data

    @pytest.mark.anyio
    async def test_get_404_no_decision(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        cid = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{uuid7()}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_404_wrong_workspace(
        self, client: AsyncClient, workspace_id: str, other_workspace_id: str,
    ) -> None:
        """Decision exists but queried from wrong workspace -> 404."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        await _create_decision(client, workspace_id, cid, li_id)

        # Query from other workspace — should 404
        resp = await client.get(
            f"/v1/workspaces/{other_workspace_id}/compiler/{cid}/decisions/{li_id}",
        )
        assert resp.status_code == 404


class TestDecisionPut:
    """B-4: PUT /v1/workspaces/{ws}/compiler/{cid}/decisions/{line_item_id}"""

    @pytest.mark.anyio
    async def test_create_new_decision(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "AI_SUGGESTED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "decision_note": "Initial suggestion",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["line_item_id"] == li_id
        assert data["state"] == "AI_SUGGESTED"

    @pytest.mark.anyio
    async def test_update_valid_transition(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """AI_SUGGESTED -> APPROVED is a valid transition."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        await _create_decision(
            client, workspace_id, cid, li_id,
            state="AI_SUGGESTED",
        )

        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "APPROVED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "decision_note": "Analyst approved",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "APPROVED"

    @pytest.mark.anyio
    async def test_update_invalid_transition_returns_409(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """AI_SUGGESTED -> LOCKED is not a valid transition -> 409."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        await _create_decision(
            client, workspace_id, cid, li_id,
            state="AI_SUGGESTED",
        )

        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "LOCKED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "decision_note": "Trying to lock directly",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_approved_requires_final_sector_code(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """APPROVED state requires final_sector_code."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "APPROVED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "final_sector_code": None,
                "decision_type": "APPROVED",
                "decision_note": "Missing final code",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_decision_response_fields(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Response must include all expected fields."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "AI_SUGGESTED",
                "suggested_sector_code": "H",
                "suggested_confidence": 0.88,
                "final_sector_code": "H",
                "decision_type": "APPROVED",
                "decision_note": "Transport mapping",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        required_fields = [
            "mapping_decision_id", "line_item_id", "compilation_id",
            "state", "suggested_sector_code", "suggested_confidence",
            "final_sector_code", "decision_type", "decision_note",
            "decided_by", "decided_at", "created_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.anyio
    async def test_excluded_requires_rationale(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """EXCLUDED state requires non-empty decision_note (rationale) -> 422."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())

        # No decision_note at all
        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "EXCLUDED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_excluded_empty_rationale_returns_422(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """EXCLUDED with empty string decision_note -> 422."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())

        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "EXCLUDED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "decision_note": "",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_excluded_whitespace_rationale_returns_422(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """EXCLUDED with whitespace-only decision_note -> 422."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())

        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "EXCLUDED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "decision_note": "   ",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_excluded_with_rationale_succeeds(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """EXCLUDED with valid rationale succeeds."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())

        resp = await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "EXCLUDED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "decision_note": "Not relevant to project scope",
                "decided_by": str(uuid7()),
            },
        )
        assert resp.status_code == 201
        assert resp.json()["state"] == "EXCLUDED"


# =========================================================================
# B-5: Bulk threshold approval
# =========================================================================


class TestBulkApprove:
    """B-5: POST /v1/workspaces/{ws}/compiler/{cid}/decisions/bulk-approve"""

    @pytest.mark.anyio
    async def test_bulk_approve_above_threshold(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Decisions with confidence >= threshold should be approved."""
        cid = await _trigger_compilation(client, workspace_id)
        li_high = str(uuid7())
        li_low = str(uuid7())

        # Create one high-confidence and one low-confidence decision
        await _create_decision(
            client, workspace_id, cid, li_high,
            state="AI_SUGGESTED", suggested_confidence=0.95,
        )
        await _create_decision(
            client, workspace_id, cid, li_low,
            state="AI_SUGGESTED", suggested_confidence=0.60,
        )

        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/bulk-approve",
            json={
                "confidence_threshold": 0.85,
                "actor": str(uuid7()),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved_count"] == 1  # Only the high-confidence one

        # Verify high-confidence is now APPROVED
        resp_high = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_high}",
        )
        assert resp_high.json()["state"] == "APPROVED"

        # Verify low-confidence is still AI_SUGGESTED
        resp_low = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_low}",
        )
        assert resp_low.json()["state"] == "AI_SUGGESTED"

    @pytest.mark.anyio
    async def test_bulk_approve_default_threshold(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Without explicit threshold, default 0.85 is used."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        await _create_decision(
            client, workspace_id, cid, li_id,
            state="AI_SUGGESTED", suggested_confidence=0.90,
        )

        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/bulk-approve",
            json={"actor": str(uuid7())},
        )
        assert resp.status_code == 200
        assert resp.json()["approved_count"] == 1

    @pytest.mark.anyio
    async def test_bulk_approve_skips_non_ai_suggested(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Only AI_SUGGESTED decisions should be bulk-approved."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())

        # Create and then approve (AI_SUGGESTED -> APPROVED)
        await _create_decision(
            client, workspace_id, cid, li_id,
            state="AI_SUGGESTED", suggested_confidence=0.95,
        )
        await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "APPROVED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.95,
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "decision_note": "Already approved",
                "decided_by": str(uuid7()),
            },
        )

        # Now bulk-approve — should find 0 eligible
        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/bulk-approve",
            json={
                "confidence_threshold": 0.85,
                "actor": str(uuid7()),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["approved_count"] == 0

    @pytest.mark.anyio
    async def test_bulk_approve_empty_compilation(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Bulk approve on compilation with no decisions -> 0 approved."""
        cid = await _trigger_compilation(client, workspace_id)
        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/bulk-approve",
            json={
                "confidence_threshold": 0.85,
                "actor": str(uuid7()),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["approved_count"] == 0

    @pytest.mark.anyio
    async def test_bulk_approve_response_fields(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Response must include approved_count and total_eligible."""
        cid = await _trigger_compilation(client, workspace_id)
        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/bulk-approve",
            json={
                "confidence_threshold": 0.85,
                "actor": str(uuid7()),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "approved_count" in data
        assert "total_eligible" in data

    @pytest.mark.anyio
    async def test_bulk_approve_threshold_zero_approves_all(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """threshold=0.0 should approve every AI_SUGGESTED decision."""
        cid = await _trigger_compilation(client, workspace_id)
        li_high = str(uuid7())
        li_low = str(uuid7())

        await _create_decision(
            client, workspace_id, cid, li_high,
            state="AI_SUGGESTED", suggested_confidence=0.95,
        )
        await _create_decision(
            client, workspace_id, cid, li_low,
            state="AI_SUGGESTED", suggested_confidence=0.10,
        )

        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/bulk-approve",
            json={
                "confidence_threshold": 0.0,
                "actor": str(uuid7()),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved_count"] == 2

    @pytest.mark.anyio
    async def test_bulk_approve_threshold_one_approves_none_below(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """threshold=1.0 should approve nothing when all confidence < 1.0."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())

        await _create_decision(
            client, workspace_id, cid, li_id,
            state="AI_SUGGESTED", suggested_confidence=0.99,
        )

        resp = await client.post(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/bulk-approve",
            json={
                "confidence_threshold": 1.0,
                "actor": str(uuid7()),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["approved_count"] == 0


# =========================================================================
# B-8: Mapping audit trail
# =========================================================================


class TestAuditTrail:
    """B-8: GET /v1/workspaces/{ws}/compiler/{cid}/decisions/{li}/audit"""

    @pytest.mark.anyio
    async def test_audit_trail_single_entry(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        await _create_decision(client, workspace_id, cid, li_id)

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}"
            f"/decisions/{li_id}/audit",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["state"] == "AI_SUGGESTED"
        assert "decided_by" in entry
        assert "decided_at" in entry

    @pytest.mark.anyio
    async def test_audit_trail_multiple_entries(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """After multiple state transitions, audit trail shows all entries."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())

        # State 1: AI_SUGGESTED
        await _create_decision(
            client, workspace_id, cid, li_id,
            state="AI_SUGGESTED",
        )
        # State 2: APPROVED
        await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}/decisions/{li_id}",
            json={
                "state": "APPROVED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "decision_note": "Approved by analyst",
                "decided_by": str(uuid7()),
            },
        )

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}"
            f"/decisions/{li_id}/audit",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 2
        # Should be ordered chronologically (oldest first)
        assert data["entries"][0]["state"] == "AI_SUGGESTED"
        assert data["entries"][1]["state"] == "APPROVED"

    @pytest.mark.anyio
    async def test_audit_trail_empty_returns_empty_list(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """No decisions for this line item -> empty entries."""
        cid = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}"
            f"/decisions/{uuid7()}/audit",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []

    @pytest.mark.anyio
    async def test_audit_trail_entry_fields(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Each audit entry must have required fields."""
        cid = await _trigger_compilation(client, workspace_id)
        li_id = str(uuid7())
        await _create_decision(client, workspace_id, cid, li_id)

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{cid}"
            f"/decisions/{li_id}/audit",
        )
        assert resp.status_code == 200
        entry = resp.json()["entries"][0]
        required_fields = [
            "mapping_decision_id", "state", "suggested_sector_code",
            "final_sector_code", "decision_type", "decision_note",
            "decided_by", "decided_at", "created_at",
        ]
        for field in required_fields:
            assert field in entry, f"Missing audit field: {field}"
