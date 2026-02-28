"""TDD: Seed script idempotency tests.

Verifies that running the seed twice does not create duplicate data.
Also tests the new 5-sector model and backward compatibility.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed import (
    DEMO_EMPLOYMENT_COEFFICIENTS,
    DEMO_SATELLITE_COEFFICIENTS,
    DEMO_SECTOR_CODES,
    DEMO_X_VECTOR,
    DEMO_Z_MATRIX,
    SAMPLE_SECTOR_CODES,
    SAMPLE_X_VECTOR,
    SAMPLE_Z_MATRIX,
    seed_5sector_model,
    seed_demo,
    seed_model,
    seed_workspace,
)
from src.repositories.engine import ModelDataRepository, ModelVersionRepository
from src.repositories.workspace import WorkspaceRepository


class TestSeedIdempotency:
    """Running seed_demo twice does not create duplicates."""

    @pytest.mark.anyio
    async def test_seed_demo_idempotent(self, db_session: AsyncSession) -> None:
        """Call seed_demo twice — second call should skip, not duplicate."""
        result1 = await seed_demo(db_session)
        assert result1["created"] is True

        result2 = await seed_demo(db_session)
        assert result2["created"] is False

        # Only one workspace with the demo engagement code
        repo = WorkspaceRepository(db_session)
        all_ws = await repo.list_all()
        demo_ws = [w for w in all_ws if w.engagement_code == "SG-DEMO-2026"]
        assert len(demo_ws) == 1

    @pytest.mark.anyio
    async def test_seed_demo_creates_workspace(self, db_session: AsyncSession) -> None:
        """seed_demo creates a workspace on first call."""
        result = await seed_demo(db_session)
        assert result["workspace_id"] is not None
        repo = WorkspaceRepository(db_session)
        ws = await repo.get(result["workspace_id"])
        assert ws is not None
        assert ws.client_name == "Strategic Gears (Demo)"

    @pytest.mark.anyio
    async def test_seed_demo_creates_5sector_model(self, db_session: AsyncSession) -> None:
        """seed_demo creates a 5-sector model."""
        result = await seed_demo(db_session)
        mid = result["model_version_id"]
        mv_repo = ModelVersionRepository(db_session)
        md_repo = ModelDataRepository(db_session)
        mv = await mv_repo.get(mid)
        md = await md_repo.get(mid)
        assert mv is not None
        assert mv.sector_count == 5
        assert md is not None
        assert md.sector_codes == DEMO_SECTOR_CODES


class TestNew5SectorModel:
    """Validate the 5-sector demo model data."""

    def test_sector_codes_length(self) -> None:
        assert len(DEMO_SECTOR_CODES) == 5

    def test_z_matrix_shape(self) -> None:
        assert len(DEMO_Z_MATRIX) == 5
        for row in DEMO_Z_MATRIX:
            assert len(row) == 5

    def test_x_vector_length(self) -> None:
        assert len(DEMO_X_VECTOR) == 5

    def test_satellite_coefficients_length(self) -> None:
        for key, vals in DEMO_SATELLITE_COEFFICIENTS.items():
            assert len(vals) == 5, f"{key} has {len(vals)} values, expected 5"

    def test_employment_coefficients_length(self) -> None:
        for key, vals in DEMO_EMPLOYMENT_COEFFICIENTS.items():
            assert len(vals) == 5, f"{key} has {len(vals)} values, expected 5"

    def test_spectral_radius_valid(self) -> None:
        """Leontief model requires spectral radius of A < 1."""
        import numpy as np

        z_arr = np.array(DEMO_Z_MATRIX, dtype=np.float64)
        x_arr = np.array(DEMO_X_VECTOR, dtype=np.float64)
        a_matrix = z_arr / x_arr[np.newaxis, :]
        eigenvalues = np.linalg.eigvals(a_matrix)
        spectral_radius = float(np.max(np.abs(eigenvalues)))
        assert spectral_radius < 1.0, f"Invalid model: spectral radius {spectral_radius} >= 1.0"

    @pytest.mark.anyio
    async def test_seed_5sector_model(self, db_session: AsyncSession) -> None:
        """seed_5sector_model creates a valid 5-sector model in DB."""
        mv_row, md_row = await seed_5sector_model(db_session)
        assert mv_row.sector_count == 5
        assert mv_row.checksum.startswith("sha256:")
        assert md_row.sector_codes == DEMO_SECTOR_CODES
        assert md_row.z_matrix_json == DEMO_Z_MATRIX
        assert md_row.x_vector_json == DEMO_X_VECTOR


class TestBackwardCompatibility:
    """Original 3-sector seed functions still work (Amendment 5)."""

    def test_original_constants_unchanged(self) -> None:
        """SAMPLE_* constants are the original 3-sector values."""
        assert len(SAMPLE_SECTOR_CODES) == 3
        assert SAMPLE_SECTOR_CODES == ["Agriculture", "Industry", "Services"]
        assert len(SAMPLE_Z_MATRIX) == 3
        assert len(SAMPLE_X_VECTOR) == 3

    @pytest.mark.anyio
    async def test_seed_model_still_3sector(self, db_session: AsyncSession) -> None:
        """seed_model() still creates the original 3-sector model."""
        mv_row, md_row = await seed_model(db_session)
        assert mv_row.sector_count == 3
        assert mv_row.base_year == 2019
        assert md_row.sector_codes == SAMPLE_SECTOR_CODES

    @pytest.mark.anyio
    async def test_seed_workspace_still_works(self, db_session: AsyncSession) -> None:
        """seed_workspace() still creates a workspace."""
        ws = await seed_workspace(db_session)
        assert ws.client_name == "Strategic Gears (Demo)"
