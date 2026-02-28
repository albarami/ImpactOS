"""Performance benchmark tests — MVP-14, Amendment 6.

Catches 10x regressions, NOT enforcing precise SLAs.
Generous ceilings (3-5x expected). Skipped by default (requires -m benchmark).
"""

import logging
import time

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

logger = logging.getLogger(__name__)


_MODEL_PAYLOAD = {
    "Z": [[150.0, 500.0], [200.0, 100.0]],
    "x": [1000.0, 2000.0],
    "sector_codes": ["S1", "S2"],
    "base_year": 2023,
    "source": "benchmark",
}

_SATELLITE_COEFFICIENTS = {
    "jobs_coeff": [0.01, 0.005],
    "import_ratio": [0.30, 0.20],
    "va_ratio": [0.40, 0.55],
}


@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Performance benchmarks with generous ceilings for CI stability."""

    @pytest.mark.anyio
    async def test_model_registration_latency(
        self,
        client: AsyncClient,
    ) -> None:
        """2-sector register < 2000ms."""
        start = time.perf_counter()
        resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 201
        logger.info("Model registration: %.1f ms", elapsed_ms)
        assert elapsed_ms < 2000, f"Model registration took {elapsed_ms:.0f}ms (ceiling: 2000ms)"

    @pytest.mark.anyio
    async def test_single_run_latency(
        self,
        client: AsyncClient,
    ) -> None:
        """Single run < 3000ms."""
        reg_resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        mid = reg_resp.json()["model_version_id"]
        ws_id = str(uuid7())

        start = time.perf_counter()
        resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        logger.info("Single run: %.1f ms", elapsed_ms)
        assert elapsed_ms < 3000, f"Single run took {elapsed_ms:.0f}ms (ceiling: 3000ms)"

    @pytest.mark.anyio
    async def test_batch_10_scenarios_latency(
        self,
        client: AsyncClient,
    ) -> None:
        """10-scenario batch < 15000ms."""
        reg_resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        mid = reg_resp.json()["model_version_id"]
        ws_id = str(uuid7())

        scenarios = [
            {
                "name": f"Scenario-{i}",
                "annual_shocks": {"2026": [float(50 + i * 10), 0.0]},
                "base_year": 2023,
            }
            for i in range(10)
        ]

        start = time.perf_counter()
        resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/batch",
            json={
                "model_version_id": mid,
                "scenarios": scenarios,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        logger.info("Batch 10 scenarios: %.1f ms", elapsed_ms)
        assert elapsed_ms < 15000, f"Batch took {elapsed_ms:.0f}ms (ceiling: 15000ms)"

    @pytest.mark.anyio
    async def test_feasibility_solve_latency(
        self,
        client: AsyncClient,
    ) -> None:
        """Feasibility solve < 2000ms."""
        reg_resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        mid = reg_resp.json()["model_version_id"]
        ws_id = str(uuid7())

        # Run to create result sets
        run_resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        run_id = run_resp.json()["run_id"]

        # Create constraints
        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Benchmark cap",
                "model_version_id": mid,
                "constraints": [
                    {
                        "constraint_type": "CAPACITY_CAP",
                        "applies_to": "S1",
                        "value": 40.0,
                        "unit": "SAR",
                        "confidence": "HARD",
                    },
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        start = time.perf_counter()
        resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        logger.info("Feasibility solve: %.1f ms", elapsed_ms)
        assert elapsed_ms < 2000, f"Feasibility took {elapsed_ms:.0f}ms (ceiling: 2000ms)"

    @pytest.mark.anyio
    async def test_workforce_compute_latency(
        self,
        client: AsyncClient,
    ) -> None:
        """Workforce compute < 2000ms."""
        reg_resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        mid = reg_resp.json()["model_version_id"]
        ws_id = str(uuid7())

        run_resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        run_id = run_resp.json()["run_id"]

        ec_resp = await client.post(
            f"/v1/workspaces/{ws_id}/employment-coefficients",
            json={
                "model_version_id": mid,
                "output_unit": "MILLION_SAR",
                "base_year": 2023,
                "coefficients": [
                    {
                        "sector_code": "S1",
                        "jobs_per_million_sar": 12.5,
                        "confidence": "HARD",
                        "source_description": "Benchmark",
                    },
                    {
                        "sector_code": "S2",
                        "jobs_per_million_sar": 8.0,
                        "confidence": "ESTIMATED",
                        "source_description": "Benchmark",
                    },
                ],
            },
        )
        ec_id = ec_resp.json()["employment_coefficients_id"]

        start = time.perf_counter()
        resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/workforce",
            json={"employment_coefficients_id": ec_id},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200
        logger.info("Workforce compute: %.1f ms", elapsed_ms)
        assert elapsed_ms < 2000, f"Workforce took {elapsed_ms:.0f}ms (ceiling: 2000ms)"

    @pytest.mark.anyio
    async def test_quality_compute_latency(
        self,
        client: AsyncClient,
    ) -> None:
        """Quality compute < 2000ms."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        start = time.perf_counter()
        resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/quality",
            json={
                "base_table_year": 2020,
                "current_year": 2026,
                "coverage_pct": 0.9,
                "base_table_vintage": "Benchmark",
                "inputs": [
                    {
                        "input_type": "mapping",
                        "input_data": {
                            "available_sectors": ["S1", "S2"],
                            "required_sectors": ["S1", "S2"],
                            "confidence_distribution": {"hard": 0.8, "estimated": 0.2},
                            "has_evidence_refs": True,
                            "source_description": "Benchmark",
                        },
                    },
                ],
                "freshness_sources": [
                    {
                        "name": "IO Table",
                        "type": "io_table",
                        "last_updated": "2023-01-01T00:00:00Z",
                    },
                ],
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 201
        logger.info("Quality compute: %.1f ms", elapsed_ms)
        assert elapsed_ms < 2000, f"Quality took {elapsed_ms:.0f}ms (ceiling: 2000ms)"
