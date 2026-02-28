"""Tests for the seed script — verifies sample data can be loaded into DB."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed import (
    SAMPLE_SECTOR_CODES,
    SAMPLE_X_VECTOR,
    SAMPLE_Z_MATRIX,
    seed_model,
    seed_workspace,
    seed_boq_line_items,
)
from src.repositories.documents import DocumentRepository, LineItemRepository
from src.repositories.engine import ModelDataRepository, ModelVersionRepository
from src.repositories.workspace import WorkspaceRepository


class TestSeedWorkspace:
    """seed_workspace creates a sample workspace."""

    @pytest.mark.anyio
    async def test_creates_workspace(self, db_session: AsyncSession) -> None:
        ws = await seed_workspace(db_session)
        repo = WorkspaceRepository(db_session)
        row = await repo.get(ws.workspace_id)
        assert row is not None
        assert row.client_name == "Strategic Gears (Demo)"
        assert row.classification == "INTERNAL"


class TestSeedModel:
    """seed_model registers a 3x3 IO model with data."""

    @pytest.mark.anyio
    async def test_creates_model_version(self, db_session: AsyncSession) -> None:
        mv_row, md_row = await seed_model(db_session)
        repo = ModelVersionRepository(db_session)
        fetched = await repo.get(mv_row.model_version_id)
        assert fetched is not None
        assert fetched.sector_count == 3
        assert fetched.base_year == 2019
        assert fetched.source == "GASTAT simplified 3-sector (demo)"

    @pytest.mark.anyio
    async def test_creates_model_data(self, db_session: AsyncSession) -> None:
        mv_row, md_row = await seed_model(db_session)
        repo = ModelDataRepository(db_session)
        fetched = await repo.get(mv_row.model_version_id)
        assert fetched is not None
        assert fetched.z_matrix_json == SAMPLE_Z_MATRIX
        assert fetched.x_vector_json == SAMPLE_X_VECTOR
        assert fetched.sector_codes == SAMPLE_SECTOR_CODES

    @pytest.mark.anyio
    async def test_model_checksum_valid(self, db_session: AsyncSession) -> None:
        mv_row, _ = await seed_model(db_session)
        assert mv_row.checksum.startswith("sha256:")
        assert len(mv_row.checksum) == 71  # "sha256:" + 64 hex chars


class TestSeedBoQLineItems:
    """seed_boq_line_items creates a document + line items."""

    @pytest.mark.anyio
    async def test_creates_document(self, db_session: AsyncSession) -> None:
        ws = await seed_workspace(db_session)
        doc_row, items = await seed_boq_line_items(db_session, ws.workspace_id)
        repo = DocumentRepository(db_session)
        fetched = await repo.get(doc_row.doc_id)
        assert fetched is not None
        assert fetched.filename == "sample_boq_neom_logistics.xlsx"

    @pytest.mark.anyio
    async def test_creates_line_items(self, db_session: AsyncSession) -> None:
        ws = await seed_workspace(db_session)
        doc_row, items = await seed_boq_line_items(db_session, ws.workspace_id)
        repo = LineItemRepository(db_session)
        fetched = await repo.get_by_doc(doc_row.doc_id)
        assert len(fetched) >= 10
        # Verify a few expected descriptions
        descriptions = {r.description for r in fetched}
        assert "Structural Steel Supply" in descriptions
        assert "Concrete Works (Grade 60)" in descriptions

    @pytest.mark.anyio
    async def test_line_items_have_values(self, db_session: AsyncSession) -> None:
        ws = await seed_workspace(db_session)
        _, items = await seed_boq_line_items(db_session, ws.workspace_id)
        for item in items:
            assert item.total_value > 0
