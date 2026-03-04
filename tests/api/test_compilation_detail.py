"""Tests for B-17: GET compilation detail.

GET /v1/workspaces/{ws}/compiler/{compilation_id}  — B-17
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.repositories.compiler import CompilationRepository
from src.repositories.mapping_decisions import MappingDecisionRepository


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
            "scenario_name": "Test Scenario",
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


async def _trigger_compilation_with_ids(
    client: AsyncClient,
    workspace_id: str,
) -> tuple[str, list[str]]:
    """Trigger a compilation and return (compilation_id, [line_item_ids])."""
    li_id_1 = str(uuid7())
    li_id_2 = str(uuid7())
    resp = await client.post(
        f"/v1/workspaces/{workspace_id}/compiler/compile",
        json={
            "scenario_name": "Test Scenario",
            "base_model_version_id": str(uuid7()),
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2028,
            "line_items": [
                {
                    "line_item_id": li_id_1,
                    "raw_text": "concrete works for building foundation",
                    "total_value": 500000.0,
                },
                {
                    "line_item_id": li_id_2,
                    "raw_text": "transport services for materials",
                    "total_value": 100000.0,
                },
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["compilation_id"], [li_id_1, li_id_2]


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
# B-17: GET compilation detail
# =========================================================================


class TestCompilationDetail:
    @pytest.mark.anyio
    async def test_get_compilation_detail(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["compilation_id"] == comp_id
        assert "suggestions" in data
        assert "high_confidence" in data
        assert "medium_confidence" in data
        assert "low_confidence" in data
        assert "metadata" in data

    @pytest.mark.anyio
    async def test_compilation_detail_suggestions_structure(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Each suggestion should have line_item_id, sector_code, confidence, explanation."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) >= 1
        suggestion = data["suggestions"][0]
        assert "line_item_id" in suggestion
        assert "sector_code" in suggestion
        assert "confidence" in suggestion
        assert "explanation" in suggestion

    @pytest.mark.anyio
    async def test_compilation_detail_404(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{uuid7()}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_compilation_detail_wrong_workspace_404(
        self, client: AsyncClient, workspace_id: str, other_workspace_id: str,
    ) -> None:
        """Compilation exists but queried from wrong workspace -> 404."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{other_workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_compilation_detail_metadata(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Detail should include metadata about the compilation input."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metadata" in data
        # metadata should include the input information
        assert isinstance(data["metadata"], dict)

    @pytest.mark.anyio
    async def test_compilation_detail_confidence_counts(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Confidence counts should be non-negative integers."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["high_confidence"], int)
        assert isinstance(data["medium_confidence"], int)
        assert isinstance(data["low_confidence"], int)
        assert data["high_confidence"] >= 0
        assert data["medium_confidence"] >= 0
        assert data["low_confidence"] >= 0

    @pytest.mark.anyio
    async def test_compilation_detail_has_assumption_drafts(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Detail should include assumption_drafts list."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "assumption_drafts" in data
        assert isinstance(data["assumption_drafts"], list)

    @pytest.mark.anyio
    async def test_compilation_detail_has_split_proposals(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Detail should include split_proposals list."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "split_proposals" in data
        assert isinstance(data["split_proposals"], list)

    @pytest.mark.anyio
    async def test_compilation_missing_workspace_metadata_404(
        self, client: AsyncClient, workspace_id: str,
        db_session: AsyncSession,
    ) -> None:
        """Legacy compilation with no workspace_id in metadata -> 404."""
        comp_repo = CompilationRepository(db_session)
        comp_id = uuid7()
        await comp_repo.create(
            compilation_id=comp_id,
            result_json={"mapping_suggestions": []},
            metadata_json={"document_id": None},  # no workspace_id
        )

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 404


# =========================================================================
# B-17 enhanced: per-line decision state merged into compilation detail
# =========================================================================


class TestCompilationDetailWithDecisions:
    """B-17: compilation detail with merged HITL decision state."""

    @pytest.mark.anyio
    async def test_detail_without_decisions_has_null_state(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Suggestions without decisions should have None decision fields."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        for s in data["suggestions"]:
            assert s["decision_state"] is None
            assert s["final_sector_code"] is None
            assert s["decided_by"] is None
            assert s["decided_at"] is None
        assert data["decided_count"] == 0
        assert data["status_summary"] == {}
        assert data["total_line_items"] == len(data["suggestions"])

    @pytest.mark.anyio
    async def test_detail_with_decisions_merges_state(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Suggestions with decisions should have merged state fields."""
        comp_id, li_ids = await _trigger_compilation_with_ids(
            client, workspace_id,
        )
        li_id = li_ids[0]

        await _create_decision(
            client, workspace_id, comp_id, li_id,
            state="AI_SUGGESTED",
            suggested_sector_code="F",
            suggested_confidence=0.92,
        )

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()

        # Find the suggestion for the decided line item
        matched = [
            s for s in data["suggestions"] if s["line_item_id"] == li_id
        ]
        assert len(matched) == 1
        s = matched[0]
        assert s["decision_state"] == "AI_SUGGESTED"
        assert s["decided_by"] is not None
        assert s["decided_at"] is not None

        # Other line item should still have no decision
        others = [
            s for s in data["suggestions"] if s["line_item_id"] != li_id
        ]
        for o in others:
            assert o["decision_state"] is None

    @pytest.mark.anyio
    async def test_detail_shows_latest_decision(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """After state transition, detail shows the latest state only."""
        comp_id, li_ids = await _trigger_compilation_with_ids(
            client, workspace_id,
        )
        li_id = li_ids[0]

        # AI_SUGGESTED -> APPROVED
        await _create_decision(
            client, workspace_id, comp_id, li_id,
            state="AI_SUGGESTED",
        )
        await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}"
            f"/decisions/{li_id}",
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

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        data = resp.json()
        matched = [
            s for s in data["suggestions"] if s["line_item_id"] == li_id
        ]
        assert matched[0]["decision_state"] == "APPROVED"
        assert matched[0]["final_sector_code"] == "F"

    @pytest.mark.anyio
    async def test_status_summary_counts(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """status_summary should count line items per state."""
        comp_id, li_ids = await _trigger_compilation_with_ids(
            client, workspace_id,
        )

        # Both AI_SUGGESTED first
        for li_id in li_ids:
            await _create_decision(
                client, workspace_id, comp_id, li_id,
                state="AI_SUGGESTED",
            )

        # Approve only the first one
        await client.put(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}"
            f"/decisions/{li_ids[0]}",
            json={
                "state": "APPROVED",
                "suggested_sector_code": "F",
                "suggested_confidence": 0.92,
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "decision_note": "Approved",
                "decided_by": str(uuid7()),
            },
        )

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        data = resp.json()
        assert data["total_line_items"] == 2
        assert data["decided_count"] == 2
        assert data["status_summary"]["APPROVED"] == 1
        assert data["status_summary"]["AI_SUGGESTED"] == 1

    @pytest.mark.anyio
    async def test_orphan_decision_not_counted(
        self, client: AsyncClient, workspace_id: str,
        db_session: AsyncSession,
    ) -> None:
        """Decision for unrelated line_item_id is not merged or counted."""
        comp_id, li_ids = await _trigger_compilation_with_ids(
            client, workspace_id,
        )

        # Create an orphan decision for a line_item_id NOT in the compilation
        orphan_li_id = uuid7()
        decision_repo = MappingDecisionRepository(db_session)
        await decision_repo.create(
            mapping_decision_id=uuid7(),
            line_item_id=orphan_li_id,
            scenario_spec_id=UUID(comp_id),
            state="AI_SUGGESTED",
            suggested_sector_code="A",
            suggested_confidence=0.99,
            decided_by=uuid7(),
        )

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        data = resp.json()

        # Orphan should not appear in suggestions or affect counts
        all_li_ids = [s["line_item_id"] for s in data["suggestions"]]
        assert str(orphan_li_id) not in all_li_ids
        assert data["decided_count"] == 0
        assert data["status_summary"] == {}
        assert data["total_line_items"] == len(li_ids)

    @pytest.mark.anyio
    async def test_total_line_items_equals_suggestions(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """total_line_items always equals len(suggestions)."""
        comp_id, li_ids = await _trigger_compilation_with_ids(
            client, workspace_id,
        )

        # Add decision for one item only
        await _create_decision(
            client, workspace_id, comp_id, li_ids[0],
            state="AI_SUGGESTED",
        )

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        data = resp.json()
        assert data["total_line_items"] == len(data["suggestions"])
        assert data["total_line_items"] == 2
        assert data["decided_count"] == 1

    @pytest.mark.anyio
    async def test_deterministic_tie_break(
        self, client: AsyncClient, workspace_id: str,
        db_session: AsyncSession,
    ) -> None:
        """Two decisions with same created_at: highest mapping_decision_id wins."""
        comp_id, li_ids = await _trigger_compilation_with_ids(
            client, workspace_id,
        )
        li_id = UUID(li_ids[0])
        compilation_uuid = UUID(comp_id)

        # Insert two decisions with identical created_at
        fixed_ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        decision_repo = MappingDecisionRepository(db_session)

        id_a = uuid7()
        id_b = uuid7()
        # Ensure id_b > id_a (uuid7 is monotonic, but force ordering)
        if id_a > id_b:
            id_a, id_b = id_b, id_a

        from src.db.tables import MappingDecisionRow

        # Row A: AI_SUGGESTED (lower ID)
        row_a = MappingDecisionRow(
            mapping_decision_id=id_a,
            line_item_id=li_id,
            scenario_spec_id=compilation_uuid,
            state="AI_SUGGESTED",
            suggested_sector_code="F",
            suggested_confidence=0.92,
            final_sector_code="F",
            decision_type="SUGGESTED",
            decision_note="first",
            decided_by=uuid7(),
            decided_at=fixed_ts,
            created_at=fixed_ts,
        )
        db_session.add(row_a)
        await db_session.flush()

        # Row B: APPROVED (higher ID, same timestamp)
        row_b = MappingDecisionRow(
            mapping_decision_id=id_b,
            line_item_id=li_id,
            scenario_spec_id=compilation_uuid,
            state="APPROVED",
            suggested_sector_code="F",
            suggested_confidence=0.92,
            final_sector_code="F",
            decision_type="APPROVED",
            decision_note="second",
            decided_by=uuid7(),
            decided_at=fixed_ts,
            created_at=fixed_ts,
        )
        db_session.add(row_b)
        await db_session.flush()

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        data = resp.json()
        matched = [
            s for s in data["suggestions"]
            if s["line_item_id"] == li_ids[0]
        ]
        assert len(matched) == 1
        # Higher mapping_decision_id (id_b) wins → APPROVED
        assert matched[0]["decision_state"] == "APPROVED"
        assert matched[0]["decision_note"] == "second"
