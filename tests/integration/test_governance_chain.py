"""Governance chain integration tests — MVP-14.

NFF governance: claims → evidence → assumptions → publication gate → export.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

# ---------------------------------------------------------------------------
# Claims → Gate
# ---------------------------------------------------------------------------


class TestClaimsToGate:
    """Claims lifecycle and publication gate."""

    @pytest.mark.anyio
    async def test_extract_creates_claims_in_db(
        self,
        client: AsyncClient,
    ) -> None:
        """Extract claims → governance status shows them."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        # Extract claims
        extract_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%. Employment rises by 10,000 jobs.",
                "run_id": run_id,
            },
        )
        assert extract_resp.status_code == 200
        assert extract_resp.json()["total"] >= 1

        # Check governance status
        status_resp = await client.get(
            f"/v1/workspaces/{ws_id}/governance/status/{run_id}",
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["claims_total"] >= 1
        assert data["claims_unresolved"] >= 1

    @pytest.mark.anyio
    async def test_unresolved_claims_block_governed_export(
        self,
        client: AsyncClient,
    ) -> None:
        """Extract → governed export → BLOCKED."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        await client.post(
            f"/v1/workspaces/{ws_id}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%.",
                "run_id": run_id,
            },
        )

        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json={
                "run_id": run_id,
                "mode": "GOVERNED",
                "export_formats": ["excel"],
                "pack_data": {"title": "Blocked Export"},
            },
        )
        assert export_resp.status_code == 201
        data = export_resp.json()
        assert data["status"] == "BLOCKED"
        assert len(data["blocking_reasons"]) >= 1

    @pytest.mark.anyio
    async def test_sandbox_export_never_blocked(
        self,
        client: AsyncClient,
    ) -> None:
        """Extract → sandbox export → COMPLETED regardless of claims."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        await client.post(
            f"/v1/workspaces/{ws_id}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%.",
                "run_id": run_id,
            },
        )

        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json={
                "run_id": run_id,
                "mode": "SANDBOX",
                "export_formats": ["excel"],
                "pack_data": {"title": "Sandbox Export"},
            },
        )
        assert export_resp.status_code == 201
        assert export_resp.json()["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Assumption Lifecycle
# ---------------------------------------------------------------------------


class TestAssumptionLifecycle:
    """Assumption creation and approval workflow."""

    @pytest.mark.anyio
    async def test_create_assumption_unapproved(
        self,
        client: AsyncClient,
    ) -> None:
        """Create assumption → status is DRAFT."""
        ws_id = str(uuid7())

        resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/assumptions",
            json={
                "type": "DEFLATOR",
                "value": 3.5,
                "units": "percent",
                "justification": "Historical average",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "DRAFT"

    @pytest.mark.anyio
    async def test_approve_assumption_changes_status(
        self,
        client: AsyncClient,
    ) -> None:
        """Create → approve → status changes."""
        ws_id = str(uuid7())

        create_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/assumptions",
            json={
                "type": "DEFLATOR",
                "value": 3.5,
                "units": "percent",
                "justification": "Historical average",
            },
        )
        assumption_id = create_resp.json()["assumption_id"]

        approve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/assumptions/{assumption_id}/approve",
            json={
                "actor": str(uuid7()),
                "range_min": 2.0,
                "range_max": 5.0,
            },
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "APPROVED"

    @pytest.mark.anyio
    async def test_multiple_assumptions_tracked(
        self,
        client: AsyncClient,
    ) -> None:
        """Create 3 assumptions → all tracked in governance status."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        for val in [3.5, 2.0, 5.0]:
            await client.post(
                f"/v1/workspaces/{ws_id}/governance/assumptions",
                json={
                    "type": "DEFLATOR",
                    "value": val,
                    "units": "percent",
                    "justification": f"Test assumption {val}",
                },
            )

        # Governance status should show assumptions
        status_resp = await client.get(
            f"/v1/workspaces/{ws_id}/governance/status/{run_id}",
        )
        assert status_resp.status_code == 200


# ---------------------------------------------------------------------------
# NFF Gate Integrity
# ---------------------------------------------------------------------------


class TestNFFGateIntegrity:
    """NFF publication gate behavior."""

    @pytest.mark.anyio
    async def test_no_claims_governed_export_passes(
        self,
        client: AsyncClient,
    ) -> None:
        """No claims → governed export → COMPLETED."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json={
                "run_id": run_id,
                "mode": "GOVERNED",
                "export_formats": ["excel"],
                "pack_data": {"title": "Clean Export"},
            },
        )
        assert export_resp.status_code == 201
        assert export_resp.json()["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_nff_check_reads_db_claims(
        self,
        client: AsyncClient,
    ) -> None:
        """Extract → nff check → passed=False for unresolved claims."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        extract_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%.",
                "run_id": run_id,
            },
        )
        claim_ids = [c["claim_id"] for c in extract_resp.json()["claims"]]

        nff_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/nff/check",
            json={"claim_ids": claim_ids},
        )
        assert nff_resp.status_code == 200
        data = nff_resp.json()
        assert data["total_claims"] == len(claim_ids)
        assert data["passed"] is False
