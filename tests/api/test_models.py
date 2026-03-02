"""Tests for B-14 + B-15: Model version list/detail + coefficient retrieval."""

import ast
import inspect
from pathlib import Path

import numpy as np
import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


async def _register_model(
    client: AsyncClient,
    *,
    sector_codes: list[str] | None = None,
    n: int = 3,
) -> str:
    """Register a model via the existing global endpoint."""
    codes = sector_codes or [f"S{i}" for i in range(n)]
    actual_n = len(codes)
    Z = np.random.default_rng(42).random((actual_n, actual_n)) * 0.1
    x = np.random.default_rng(42).random(actual_n) * 10.0 + 1.0
    resp = await client.post("/v1/engine/models", json={
        "Z": Z.tolist(),
        "x": x.tolist(),
        "sector_codes": codes,
        "base_year": 2023,
        "source": "test-model",
    })
    assert resp.status_code == 201
    return resp.json()["model_version_id"]


class TestListModelVersions:
    @pytest.mark.anyio
    async def test_list_empty(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_list_populated(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        await _register_model(client)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert "model_version_id" in item
        assert item["base_year"] == 2023
        assert item["sector_count"] == 3


class TestGetModelVersion:
    @pytest.mark.anyio
    async def test_get_existing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        mv_id = await _register_model(client)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_version_id"] == mv_id
        assert data["source"] == "test-model"
        assert data["checksum"].startswith("sha256:")

    @pytest.mark.anyio
    async def test_get_missing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{uuid7()}",
        )
        assert resp.status_code == 404


class TestGetCoefficients:
    @pytest.mark.anyio
    async def test_coefficients_match_model_sector_count(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Core B-15 contract: returned coefficient count matches the model's sectors."""
        mv_id = await _register_model(client, sector_codes=["A", "B", "C"])
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_version_id"] == mv_id
        assert len(data["sector_coefficients"]) == 3

    @pytest.mark.anyio
    async def test_coefficients_sector_codes_match_model(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Returned sector codes must match the model's actual sector codes."""
        codes = ["AGR", "MFG", "SRV", "CON"]
        mv_id = await _register_model(client, sector_codes=codes)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        returned_codes = [c["sector_code"] for c in resp.json()["sector_coefficients"]]
        assert returned_codes == codes

    @pytest.mark.anyio
    async def test_coefficients_different_model_sizes(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Two models with different sector counts return different-length coefficients."""
        mv_2 = await _register_model(client, sector_codes=["X", "Y"])
        mv_5 = await _register_model(client, sector_codes=["A", "B", "C", "D", "E"])

        r2 = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_2}/coefficients",
        )
        r5 = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_5}/coefficients",
        )
        assert len(r2.json()["sector_coefficients"]) == 2
        assert len(r5.json()["sector_coefficients"]) == 5

    @pytest.mark.anyio
    async def test_coefficients_va_ratios_from_model_data(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """VA ratios are computed from the model's IO data, not from a static file."""
        mv_id = await _register_model(client, sector_codes=["A", "B", "C"])
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        for coeff in resp.json()["sector_coefficients"]:
            # VA ratios must be between 0 and 1 (derived from IO model)
            assert 0.0 <= coeff["va_ratio"] <= 1.0
            # Import ratios default to 0.15
            assert coeff["import_ratio"] == pytest.approx(0.15)

    @pytest.mark.anyio
    async def test_coefficients_value_types_and_ranges(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        mv_id = await _register_model(client, sector_codes=["A", "B"])
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["source"], str)
        assert len(data["source"]) > 0
        for coeff in data["sector_coefficients"]:
            assert isinstance(coeff["sector_code"], str)
            assert isinstance(coeff["jobs_coeff"], (int, float))
            assert isinstance(coeff["import_ratio"], (int, float))
            assert isinstance(coeff["va_ratio"], (int, float))
            assert coeff["jobs_coeff"] >= 0.0
            assert coeff["import_ratio"] >= 0.0
            assert coeff["va_ratio"] >= 0.0

    @pytest.mark.anyio
    async def test_coefficients_sector_codes_unique(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        mv_id = await _register_model(client, sector_codes=["A", "B", "C", "D"])
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        codes = [c["sector_code"] for c in resp.json()["sector_coefficients"]]
        assert len(codes) == len(set(codes)), "Duplicate sector codes in coefficients"

    @pytest.mark.anyio
    async def test_coefficients_source_without_employment(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Without employment coefficients, source is 'model-data' and jobs are 0."""
        mv_id = await _register_model(client, sector_codes=["A", "B"])
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "model-data"
        for coeff in data["sector_coefficients"]:
            assert coeff["jobs_coeff"] == 0.0

    @pytest.mark.anyio
    async def test_coefficients_with_employment_data(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """When employment coefficients are registered, they appear in the response."""
        mv_id = await _register_model(client, sector_codes=["A", "B"])
        # Register employment coefficients via the workforce API
        ec_resp = await client.post(
            f"/v1/workspaces/{workspace_id}/employment-coefficients",
            json={
                "model_version_id": mv_id,
                "output_unit": "MILLION_SAR",
                "base_year": 2023,
                "coefficients": [
                    {"sector_code": "A", "jobs_per_million_sar": 5.5,
                     "confidence": "HIGH", "source_description": "test"},
                    {"sector_code": "B", "jobs_per_million_sar": 3.2,
                     "confidence": "MEDIUM", "source_description": "test"},
                ],
            },
        )
        assert ec_resp.status_code == 201

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "model-data+employment"
        coeffs = {c["sector_code"]: c for c in data["sector_coefficients"]}
        assert coeffs["A"]["jobs_coeff"] == pytest.approx(5.5)
        assert coeffs["B"]["jobs_coeff"] == pytest.approx(3.2)

    @pytest.mark.anyio
    async def test_coefficients_missing_model(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{uuid7()}/coefficients",
        )
        assert resp.status_code == 404


class TestNoSyntheticInRuntime:
    """Guardrail: B-15 code path must never import from data/synthetic."""

    def test_models_py_has_no_synthetic_imports(self) -> None:
        """src/api/models.py must not reference synthetic data paths."""
        source_path = Path(inspect.getfile(inspect.getmodule(
            __import__("src.api.models", fromlist=["models"]),
        ))).resolve()  # type: ignore[arg-type]
        source_text = source_path.read_text(encoding="utf-8")
        assert "synthetic" not in source_text.lower(), (
            f"src/api/models.py contains 'synthetic' reference: "
            f"runtime B-15 code must not use synthetic data"
        )
        assert "data/synthetic" not in source_text, (
            "src/api/models.py references data/synthetic path"
        )

    def test_api_layer_no_synthetic_imports(self) -> None:
        """No file in src/api/ should import from data/synthetic at module level."""
        api_dir = Path(__file__).resolve().parent.parent.parent / "src" / "api"
        violations: list[str] = []
        for py_file in api_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if "synthetic" in node.module:
                        violations.append(f"{py_file.name}: imports {node.module}")
        assert not violations, (
            f"API layer imports synthetic modules: {violations}"
        )
