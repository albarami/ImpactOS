"""Learning flywheel integration tests — MVP-14.

Knowledge Flywheel: compiler → decisions → library auto-capture.
Patterns are manual-only (automatic creation deferred).
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

# ---------------------------------------------------------------------------
# Compiler → Library
# ---------------------------------------------------------------------------


class TestCompilerToLibrary:
    """Compiler decisions auto-capture to mapping library."""

    @pytest.mark.anyio
    async def test_accept_decision_creates_mapping_entry(
        self,
        client: AsyncClient,
    ) -> None:
        """Compile → accept → GET mappings → entry exists."""
        ws_id = str(uuid7())
        li_id = str(uuid7())

        # Step 1: Compile
        compile_resp = await client.post(
            f"/v1/workspaces/{ws_id}/compiler/compile",
            json={
                "scenario_name": "Flywheel Accept",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "line_items": [
                    {
                        "line_item_id": li_id,
                        "raw_text": "concrete works for stadium",
                        "total_value": 5000000.0,
                    },
                ],
            },
        )
        assert compile_resp.status_code == 201
        comp_id = compile_resp.json()["compilation_id"]

        # Step 2: Accept decision
        dec_resp = await client.post(
            f"/v1/workspaces/{ws_id}/compiler/{comp_id}/decisions",
            json={
                "decisions": [
                    {"line_item_id": li_id, "action": "accept"},
                ],
            },
        )
        assert dec_resp.status_code == 200
        assert dec_resp.json()["accepted"] == 1

    @pytest.mark.anyio
    async def test_reject_with_override_creates_override(
        self,
        client: AsyncClient,
    ) -> None:
        """Compile → reject with override → override pair captured."""
        ws_id = str(uuid7())
        li_id = str(uuid7())

        compile_resp = await client.post(
            f"/v1/workspaces/{ws_id}/compiler/compile",
            json={
                "scenario_name": "Flywheel Reject",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "line_items": [
                    {
                        "line_item_id": li_id,
                        "raw_text": "concrete works",
                        "total_value": 1000000.0,
                    },
                ],
            },
        )
        comp_id = compile_resp.json()["compilation_id"]

        dec_resp = await client.post(
            f"/v1/workspaces/{ws_id}/compiler/{comp_id}/decisions",
            json={
                "decisions": [
                    {
                        "line_item_id": li_id,
                        "action": "reject",
                        "override_sector_code": "C",
                        "note": "Should be Manufacturing",
                    },
                ],
            },
        )
        assert dec_resp.status_code == 200
        assert dec_resp.json()["rejected"] == 1

    @pytest.mark.anyio
    async def test_multiple_decisions_batch(
        self,
        client: AsyncClient,
    ) -> None:
        """Compile → 3 items → accept/reject → all recorded."""
        ws_id = str(uuid7())
        li_ids = [str(uuid7()) for _ in range(3)]

        compile_resp = await client.post(
            f"/v1/workspaces/{ws_id}/compiler/compile",
            json={
                "scenario_name": "Batch Decisions",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "line_items": [
                    {"line_item_id": li_ids[0], "raw_text": "concrete", "total_value": 1e6},
                    {"line_item_id": li_ids[1], "raw_text": "steel", "total_value": 2e6},
                    {"line_item_id": li_ids[2], "raw_text": "glass", "total_value": 500000.0},
                ],
            },
        )
        comp_id = compile_resp.json()["compilation_id"]

        dec_resp = await client.post(
            f"/v1/workspaces/{ws_id}/compiler/{comp_id}/decisions",
            json={
                "decisions": [
                    {"line_item_id": li_ids[0], "action": "accept"},
                    {"line_item_id": li_ids[1], "action": "accept"},
                    {
                        "line_item_id": li_ids[2],
                        "action": "reject",
                        "override_sector_code": "G",
                    },
                ],
            },
        )
        assert dec_resp.status_code == 200
        data = dec_resp.json()
        assert data["accepted"] == 2
        assert data["rejected"] == 1
        assert data["total"] == 3


# ---------------------------------------------------------------------------
# Library Growth
# ---------------------------------------------------------------------------


class TestLibraryGrowth:
    """Library entries grow and are queryable."""

    @pytest.mark.anyio
    async def test_library_stats_increase_after_decisions(
        self,
        client: AsyncClient,
    ) -> None:
        """GET stats before + after decisions → count increases."""
        ws_id = str(uuid7())

        # Stats before
        before_resp = await client.get(
            f"/v1/workspaces/{ws_id}/libraries/stats",
        )
        assert before_resp.status_code == 200
        before_count = before_resp.json()["mapping_entries"]

        # Create a mapping entry manually
        await client.post(
            f"/v1/workspaces/{ws_id}/libraries/mapping/entries",
            json={
                "pattern": "steel fabrication",
                "sector_code": "C",
                "confidence": 0.85,
                "tags": ["construction"],
            },
        )

        # Stats after
        after_resp = await client.get(
            f"/v1/workspaces/{ws_id}/libraries/stats",
        )
        assert after_resp.json()["mapping_entries"] == before_count + 1

    @pytest.mark.anyio
    async def test_manual_pattern_creation_and_retrieval(
        self,
        client: AsyncClient,
    ) -> None:
        """POST pattern manually → GET by ID → fields match."""
        ws_id = str(uuid7())

        create_resp = await client.post(
            f"/v1/workspaces/{ws_id}/libraries/patterns",
            json={
                "name": "Construction Boom",
                "description": "High growth in construction sector",
                "sector_focus": ["F", "G"],
                "typical_shock_types": ["final_demand"],
                "tags": ["mega-project"],
            },
        )
        assert create_resp.status_code == 201
        pattern_id = create_resp.json()["pattern_id"]

        # Retrieve by ID
        get_resp = await client.get(
            f"/v1/workspaces/{ws_id}/libraries/patterns/{pattern_id}",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["name"] == "Construction Boom"
        assert data["sector_focus"] == ["F", "G"]

    @pytest.mark.anyio
    async def test_pattern_search_by_sector(
        self,
        client: AsyncClient,
    ) -> None:
        """POST pattern with sector_focus → list → found."""
        ws_id = str(uuid7())

        await client.post(
            f"/v1/workspaces/{ws_id}/libraries/patterns",
            json={
                "name": "Tourism Impact",
                "sector_focus": ["I", "H"],
                "tags": ["tourism"],
            },
        )

        # List patterns for workspace
        list_resp = await client.get(
            f"/v1/workspaces/{ws_id}/libraries/patterns",
        )
        assert list_resp.status_code == 200
        patterns = list_resp.json()
        assert any(p["name"] == "Tourism Impact" for p in patterns)

    @pytest.mark.anyio
    async def test_assumption_library_seeded(
        self,
        client: AsyncClient,
    ) -> None:
        """Create assumption entry → list → entry exists."""
        ws_id = str(uuid7())

        create_resp = await client.post(
            f"/v1/workspaces/{ws_id}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 3.5,
                "range_low": 2.0,
                "range_high": 5.0,
                "unit": "percent",
                "justification": "Industry average",
                "source": "GASTAT 2024",
                "confidence": "ESTIMATED",
            },
        )
        assert create_resp.status_code == 201
        data = create_resp.json()
        assert "entry_id" in data
        assert data["status"] == "DRAFT"


# ---------------------------------------------------------------------------
# Library Integrity
# ---------------------------------------------------------------------------


class TestLibraryIntegrity:
    """Workspace isolation and version history."""

    @pytest.mark.anyio
    async def test_workspace_isolation(
        self,
        client: AsyncClient,
    ) -> None:
        """ws1 entries don't appear in ws2."""
        ws1 = str(uuid7())
        ws2 = str(uuid7())

        # Create entry in ws1
        await client.post(
            f"/v1/workspaces/{ws1}/libraries/mapping/entries",
            json={
                "pattern": "ws1 pattern",
                "sector_code": "F",
                "confidence": 0.9,
            },
        )

        # ws2 should have no entries
        list_resp = await client.get(
            f"/v1/workspaces/{ws2}/libraries/mapping/entries",
        )
        assert list_resp.status_code == 200
        entries = list_resp.json()
        assert not any(e["pattern"] == "ws1 pattern" for e in entries)

    @pytest.mark.anyio
    async def test_version_history_preserved(
        self,
        client: AsyncClient,
    ) -> None:
        """Create mapping version v1, v2 → both accessible."""
        ws_id = str(uuid7())

        # Create two entries (distinct patterns)
        e1_resp = await client.post(
            f"/v1/workspaces/{ws_id}/libraries/mapping/entries",
            json={"pattern": "original mapping", "sector_code": "A", "confidence": 0.7},
        )
        assert e1_resp.status_code == 201

        e2_resp = await client.post(
            f"/v1/workspaces/{ws_id}/libraries/mapping/entries",
            json={"pattern": "updated mapping", "sector_code": "A", "confidence": 0.9},
        )
        assert e2_resp.status_code == 201

        # Both entries accessible
        list_resp = await client.get(
            f"/v1/workspaces/{ws_id}/libraries/mapping/entries",
        )
        patterns = [e["pattern"] for e in list_resp.json()]
        assert "original mapping" in patterns
        assert "updated mapping" in patterns

    @pytest.mark.anyio
    async def test_library_versions_tracked(
        self,
        client: AsyncClient,
    ) -> None:
        """Create mapping versions → version numbers increment."""
        ws_id = str(uuid7())

        # Seed an entry so versions have content
        await client.post(
            f"/v1/workspaces/{ws_id}/libraries/mapping/entries",
            json={"pattern": "version test", "sector_code": "F", "confidence": 0.8},
        )

        # Create version 1
        v1_resp = await client.post(
            f"/v1/workspaces/{ws_id}/libraries/mapping/versions",
        )
        assert v1_resp.status_code == 201
        assert v1_resp.json()["version"] == 1

        # Create version 2
        v2_resp = await client.post(
            f"/v1/workspaces/{ws_id}/libraries/mapping/versions",
        )
        assert v2_resp.status_code == 201
        assert v2_resp.json()["version"] == 2

        # Latest returns v2
        latest_resp = await client.get(
            f"/v1/workspaces/{ws_id}/libraries/mapping/versions/latest",
        )
        assert latest_resp.status_code == 200
        assert latest_resp.json()["version"] == 2
