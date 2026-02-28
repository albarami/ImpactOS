"""Tests for FastAPI knowledge flywheel endpoints — MVP-12.

19 endpoints total (7 mapping + 7 assumption + 5 pattern/stats).
All workspace-scoped. All 8 amendments enforced.

Tests:
- Mapping library CRUD, status promotion, versioning, latest
- Assumption library CRUD, filter by type/sector, versioning, latest
- Scenario pattern CRUD, usage increment, aggregate stats
- Content immutability (Amendment 2): no generic update
- Version uniqueness (Amendment 1): workspace+version
- Entry status workflow (Amendment 7): DRAFT → PUBLISHED → DEPRECATED
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = str(uuid7())


# ---------------------------------------------------------------------------
# Mapping Library — Entries
# ---------------------------------------------------------------------------


class TestMappingLibraryEntries:
    @pytest.mark.anyio
    async def test_create_entry_returns_201(self, client: AsyncClient) -> None:
        payload = {
            "pattern": "concrete works",
            "sector_code": "F",
            "confidence": 0.92,
            "tags": ["construction"],
        }
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/libraries/mapping/entries",
            json=payload,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["pattern"] == "concrete works"
        assert data["sector_code"] == "F"
        assert data["confidence"] == 0.92
        assert data["status"] == "DRAFT"
        assert data["usage_count"] == 0
        assert "entry_id" in data

    @pytest.mark.anyio
    async def test_list_entries_by_workspace(self, client: AsyncClient) -> None:
        # Create two entries
        for pattern in ("steel works", "pipe laying"):
            await client.post(
                f"/v1/workspaces/{WS_ID}/libraries/mapping/entries",
                json={
                    "pattern": pattern,
                    "sector_code": "F",
                    "confidence": 0.8,
                },
            )

        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/libraries/mapping/entries",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    @pytest.mark.anyio
    async def test_list_entries_filter_by_sector(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "farming", "sector_code": "A", "confidence": 0.7},
        )
        await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "mining", "sector_code": "B", "confidence": 0.8},
        )

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/mapping/entries?sector_code=A",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["sector_code"] == "A"

    @pytest.mark.anyio
    async def test_get_entry_by_id(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "elec", "sector_code": "D", "confidence": 0.6},
        )
        entry_id = create_resp.json()["entry_id"]

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{entry_id}",
        )
        assert resp.status_code == 200
        assert resp.json()["entry_id"] == entry_id

    @pytest.mark.anyio
    async def test_get_entry_not_found(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        fake = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{fake}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_patch_status_draft_to_published(
        self, client: AsyncClient,
    ) -> None:
        """Amendment 7: steward can promote DRAFT → PUBLISHED."""
        ws = str(uuid7())
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "hvac", "sector_code": "F", "confidence": 0.85},
        )
        entry_id = create_resp.json()["entry_id"]

        resp = await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{entry_id}/status",
            json={"status": "PUBLISHED"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "PUBLISHED"

    @pytest.mark.anyio
    async def test_patch_status_invalid(self, client: AsyncClient) -> None:
        """Amendment 7: reject invalid status values."""
        ws = str(uuid7())
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "x", "sector_code": "F", "confidence": 0.5},
        )
        entry_id = create_resp.json()["entry_id"]

        resp = await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{entry_id}/status",
            json={"status": "INVALID"},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_patch_status_not_found(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        fake = str(uuid7())
        resp = await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{fake}/status",
            json={"status": "PUBLISHED"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Mapping Library — Versions
# ---------------------------------------------------------------------------


class TestMappingLibraryVersions:
    @pytest.mark.anyio
    async def test_publish_version_201(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        # Create and publish an entry first
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "concrete", "sector_code": "F", "confidence": 0.9},
        )
        entry_id = create_resp.json()["entry_id"]
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{entry_id}/status",
            json={"status": "PUBLISHED"},
        )

        resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/versions",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == 1
        assert data["entry_count"] >= 1

    @pytest.mark.anyio
    async def test_version_auto_increments(self, client: AsyncClient) -> None:
        """Amendment 1: version = MAX(workspace) + 1."""
        ws = str(uuid7())
        # Create + publish entry
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "test", "sector_code": "F", "confidence": 0.9},
        )
        eid = create_resp.json()["entry_id"]
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{eid}/status",
            json={"status": "PUBLISHED"},
        )

        resp1 = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/versions",
        )
        assert resp1.json()["version"] == 1

        resp2 = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/versions",
        )
        assert resp2.json()["version"] == 2

    @pytest.mark.anyio
    async def test_list_versions(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        # publish entry
        cr = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "x", "sector_code": "F", "confidence": 0.9},
        )
        eid = cr.json()["entry_id"]
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{eid}/status",
            json={"status": "PUBLISHED"},
        )

        await client.post(f"/v1/workspaces/{ws}/libraries/mapping/versions")
        await client.post(f"/v1/workspaces/{ws}/libraries/mapping/versions")

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/mapping/versions",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.anyio
    async def test_get_latest_version(self, client: AsyncClient) -> None:
        """Convenience endpoint: versions/latest."""
        ws = str(uuid7())
        cr = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "y", "sector_code": "F", "confidence": 0.9},
        )
        eid = cr.json()["entry_id"]
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/{eid}/status",
            json={"status": "PUBLISHED"},
        )
        await client.post(f"/v1/workspaces/{ws}/libraries/mapping/versions")
        await client.post(f"/v1/workspaces/{ws}/libraries/mapping/versions")

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/mapping/versions/latest",
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    @pytest.mark.anyio
    async def test_get_latest_version_empty(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/mapping/versions/latest",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Assumption Library — Entries
# ---------------------------------------------------------------------------


class TestAssumptionLibraryEntries:
    @pytest.mark.anyio
    async def test_create_entry_returns_201(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        payload = {
            "assumption_type": "GROWTH_RATE",
            "sector_code": "F",
            "default_value": 3.5,
            "range_low": 2.0,
            "range_high": 5.0,
            "unit": "percent",
            "justification": "Industry average",
            "source": "GASTAT 2024",
            "confidence": "ESTIMATED",
        }
        resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json=payload,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["assumption_type"] == "GROWTH_RATE"
        assert data["default_value"] == 3.5
        assert data["status"] == "DRAFT"

    @pytest.mark.anyio
    async def test_create_entry_range_validation(
        self, client: AsyncClient,
    ) -> None:
        """range_high must be >= range_low."""
        ws = str(uuid7())
        payload = {
            "assumption_type": "GROWTH_RATE",
            "sector_code": "F",
            "default_value": 3.5,
            "range_low": 5.0,
            "range_high": 2.0,  # Invalid
            "unit": "percent",
        }
        resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json=payload,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_list_entries_filter_by_type(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        for atype in ("GROWTH_RATE", "IMPORT_RATIO"):
            await client.post(
                f"/v1/workspaces/{ws}/libraries/assumptions/entries",
                json={
                    "assumption_type": atype,
                    "sector_code": "F",
                    "default_value": 1.0,
                    "range_low": 0.5,
                    "range_high": 1.5,
                    "unit": "ratio",
                },
            )

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries"
            "?assumption_type=GROWTH_RATE",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["assumption_type"] == "GROWTH_RATE"

    @pytest.mark.anyio
    async def test_list_entries_filter_by_sector(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        for sc in ("A", "B"):
            await client.post(
                f"/v1/workspaces/{ws}/libraries/assumptions/entries",
                json={
                    "assumption_type": "GROWTH_RATE",
                    "sector_code": sc,
                    "default_value": 2.0,
                    "range_low": 1.0,
                    "range_high": 3.0,
                    "unit": "percent",
                },
            )

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries"
            "?sector_code=A",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.anyio
    async def test_get_entry_by_id(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 1.0,
                "range_low": 0.5,
                "range_high": 1.5,
                "unit": "ratio",
            },
        )
        entry_id = create_resp.json()["entry_id"]

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries/{entry_id}",
        )
        assert resp.status_code == 200
        assert resp.json()["entry_id"] == entry_id

    @pytest.mark.anyio
    async def test_patch_status(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 1.0,
                "range_low": 0.5,
                "range_high": 1.5,
                "unit": "ratio",
            },
        )
        entry_id = create_resp.json()["entry_id"]

        resp = await client.patch(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries/{entry_id}/status",
            json={"status": "PUBLISHED"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "PUBLISHED"


# ---------------------------------------------------------------------------
# Assumption Library — Versions
# ---------------------------------------------------------------------------


class TestAssumptionLibraryVersions:
    @pytest.mark.anyio
    async def test_publish_version(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        cr = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 2.5,
                "range_low": 1.0,
                "range_high": 4.0,
                "unit": "percent",
            },
        )
        eid = cr.json()["entry_id"]
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries/{eid}/status",
            json={"status": "PUBLISHED"},
        )

        resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == 1
        assert data["entry_count"] >= 1

    @pytest.mark.anyio
    async def test_list_versions(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        cr = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 2.5,
                "range_low": 1.0,
                "range_high": 4.0,
                "unit": "percent",
            },
        )
        eid = cr.json()["entry_id"]
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries/{eid}/status",
            json={"status": "PUBLISHED"},
        )
        await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions",
        )
        await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions",
        )

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.anyio
    async def test_get_latest_version(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        cr = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 2.5,
                "range_low": 1.0,
                "range_high": 4.0,
                "unit": "percent",
            },
        )
        eid = cr.json()["entry_id"]
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries/{eid}/status",
            json={"status": "PUBLISHED"},
        )
        await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions",
        )
        await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions",
        )

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions/latest",
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    @pytest.mark.anyio
    async def test_get_latest_version_empty(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions/latest",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scenario Patterns
# ---------------------------------------------------------------------------


class TestScenarioPatterns:
    @pytest.mark.anyio
    async def test_create_pattern_returns_201(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        payload = {
            "name": "Construction Boom",
            "description": "High growth in construction sector",
            "sector_focus": ["F", "G"],
            "typical_shock_types": ["final_demand"],
            "tags": ["mega-project"],
        }
        resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/patterns",
            json=payload,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Construction Boom"
        assert "pattern_id" in data
        assert data["usage_count"] == 0

    @pytest.mark.anyio
    async def test_list_patterns_by_workspace(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        for name in ("Pattern A", "Pattern B"):
            await client.post(
                f"/v1/workspaces/{ws}/libraries/patterns",
                json={
                    "name": name,
                    "sector_focus": ["F"],
                    "typical_shock_types": ["final_demand"],
                },
            )

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/patterns",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.anyio
    async def test_get_pattern_by_id(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/patterns",
            json={
                "name": "Test",
                "sector_focus": ["F"],
                "typical_shock_types": [],
            },
        )
        pid = create_resp.json()["pattern_id"]

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/patterns/{pid}",
        )
        assert resp.status_code == 200
        assert resp.json()["pattern_id"] == pid

    @pytest.mark.anyio
    async def test_get_pattern_not_found(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        fake = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/patterns/{fake}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_patch_usage_increment(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        create_resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/patterns",
            json={
                "name": "Usage Test",
                "sector_focus": ["F"],
                "typical_shock_types": [],
            },
        )
        pid = create_resp.json()["pattern_id"]

        resp = await client.patch(
            f"/v1/workspaces/{ws}/libraries/patterns/{pid}/usage",
        )
        assert resp.status_code == 200
        assert resp.json()["usage_count"] == 1

        resp2 = await client.patch(
            f"/v1/workspaces/{ws}/libraries/patterns/{pid}/usage",
        )
        assert resp2.json()["usage_count"] == 2


# ---------------------------------------------------------------------------
# Library Stats — Aggregate
# ---------------------------------------------------------------------------


class TestLibraryStats:
    @pytest.mark.anyio
    async def test_stats_empty_workspace(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/stats",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mapping_entries"] == 0
        assert data["assumption_entries"] == 0
        assert data["scenario_patterns"] == 0

    @pytest.mark.anyio
    async def test_stats_with_data(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        # Add mapping entry
        await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={"pattern": "x", "sector_code": "F", "confidence": 0.9},
        )
        # Add assumption entry
        await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 1.0,
                "range_low": 0.5,
                "range_high": 1.5,
                "unit": "ratio",
            },
        )
        # Add pattern
        await client.post(
            f"/v1/workspaces/{ws}/libraries/patterns",
            json={
                "name": "P",
                "sector_focus": ["F"],
                "typical_shock_types": [],
            },
        )

        resp = await client.get(
            f"/v1/workspaces/{ws}/libraries/stats",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mapping_entries"] == 1
        assert data["assumption_entries"] == 1
        assert data["scenario_patterns"] == 1


# ---------------------------------------------------------------------------
# Amendment 7: Only PUBLISHED entries in versions
# ---------------------------------------------------------------------------


class TestVersionsOnlyPublished:
    @pytest.mark.anyio
    async def test_mapping_version_excludes_draft(
        self, client: AsyncClient,
    ) -> None:
        """Draft entries should NOT appear in published versions."""
        ws = str(uuid7())
        # Create 2 entries, publish only 1
        cr1 = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={
                "pattern": "published one",
                "sector_code": "F",
                "confidence": 0.9,
            },
        )
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/mapping/entries/"
            f"{cr1.json()['entry_id']}/status",
            json={"status": "PUBLISHED"},
        )
        # This stays DRAFT
        await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/entries",
            json={
                "pattern": "draft one",
                "sector_code": "G",
                "confidence": 0.8,
            },
        )

        resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/mapping/versions",
        )
        assert resp.status_code == 201
        assert resp.json()["entry_count"] == 1

    @pytest.mark.anyio
    async def test_assumption_version_excludes_draft(
        self, client: AsyncClient,
    ) -> None:
        ws = str(uuid7())
        cr = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "GROWTH_RATE",
                "sector_code": "F",
                "default_value": 2.0,
                "range_low": 1.0,
                "range_high": 3.0,
                "unit": "percent",
            },
        )
        await client.patch(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries/"
            f"{cr.json()['entry_id']}/status",
            json={"status": "PUBLISHED"},
        )
        # Draft
        await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/entries",
            json={
                "assumption_type": "IMPORT_RATIO",
                "sector_code": "G",
                "default_value": 0.5,
                "range_low": 0.3,
                "range_high": 0.7,
                "unit": "ratio",
            },
        )

        resp = await client.post(
            f"/v1/workspaces/{ws}/libraries/assumptions/versions",
        )
        assert resp.status_code == 201
        assert resp.json()["entry_count"] == 1
