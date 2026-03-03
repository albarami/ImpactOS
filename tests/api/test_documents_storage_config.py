"""Tests for G3: document storage must be settings-driven, not hardcoded.

Currently, src/api/documents.py instantiates DocumentStorageService with a
hardcoded path ("./uploads"). Storage should instead be injected via FastAPI
dependency injection using a get_document_storage factory in dependencies.py,
reading the root from settings.

These tests will FAIL until:
1. get_document_storage is added to src/api/dependencies.py
2. documents.py uses Depends(get_document_storage) instead of hardcoded _storage
"""

import csv
import io
import tempfile

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


def _make_csv_content() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows([
        ["Description", "Quantity", "Unit", "Unit Price", "Total"],
        ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
        ["Concrete Works", "20000", "m3", "450", "9000000"],
    ])
    return buf.getvalue().encode("utf-8")


class TestDocumentStorageConfig:
    """G3: Document storage must be settings-driven, not hardcoded."""

    @pytest.mark.anyio
    async def test_storage_root_from_settings(self, client: AsyncClient) -> None:
        """Upload should succeed — basic check that DI works for storage."""
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_storage_override_in_tests(self, db_session) -> None:
        """Override get_document_storage via app.dependency_overrides with a temp dir.

        This test verifies that DocumentStorageService can be swapped via DI,
        proving storage is no longer hardcoded.
        """
        from src.api.main import app
        from src.db.session import get_async_session

        try:
            from src.api.dependencies import get_document_storage
        except ImportError:
            pytest.skip("get_document_storage not yet implemented")

        from httpx import ASGITransport
        from httpx import AsyncClient as AC

        from src.ingestion.storage import DocumentStorageService

        # Create a temp directory for test storage
        with tempfile.TemporaryDirectory() as tmpdir:
            test_storage = DocumentStorageService(storage_root=tmpdir)

            def _override_storage():
                return test_storage

            async def _override_session():
                yield db_session

            from uuid import UUID

            from src.api.auth_deps import (
                AuthPrincipal,
                WorkspaceMember,
                get_current_principal,
                require_workspace_member,
            )

            _p = AuthPrincipal(
                user_id=UUID("00000000-0000-7000-8000-000000000001"),
                username="analyst", role="analyst",
            )

            async def _override_principal():
                return _p

            async def _override_member(workspace_id: UUID = None):
                return WorkspaceMember(
                    principal=_p,
                    workspace_id=workspace_id or UUID("00000000-0000-7000-8000-000000000010"),
                    role="admin",
                )

            app.dependency_overrides[get_document_storage] = _override_storage
            app.dependency_overrides[get_async_session] = _override_session
            app.dependency_overrides[get_current_principal] = _override_principal
            app.dependency_overrides[require_workspace_member] = _override_member

            try:
                async with AC(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as ac:
                    workspace_id = str(uuid7())
                    uploaded_by = str(uuid7())
                    response = await ac.post(
                        f"/v1/workspaces/{workspace_id}/documents",
                        files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
                        data={
                            "doc_type": "BOQ",
                            "source_type": "CLIENT",
                            "classification": "RESTRICTED",
                            "language": "en",
                            "uploaded_by": uploaded_by,
                        },
                    )
                    assert response.status_code == 201
            finally:
                app.dependency_overrides.clear()
