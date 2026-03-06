"""Tests for scripts/staging_full_e2e.py -- full-system E2E acceptance harness.

Follows the same mock patterns as test_staging_smoke.py:
- _mock_response() builds httpx.Response mocks
- _mock_client() routes URL substrings to responses
- Each stage function is tested independently
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.staging_full_e2e import (
    E2EContext,
    E2EReport,
    StageResult,
    run_e2e,
    stage_api_health,
    stage_copilot_reachable,
    stage_document_upload,
    stage_export_create,
    stage_export_download,
    stage_frontend_reachable,
    stage_governance_check,
    stage_scenario_run,
    stage_workspace_access,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status_code: int,
    json_body: dict | None = None,
    text: str = "",
    content: bytes = b"",
) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("No JSON body")
    resp.text = text or json.dumps(json_body) if json_body else ""
    resp.content = content or resp.text.encode()
    resp.headers = {"content-type": "text/html" if not json_body else "application/json"}
    return resp


def _make_ctx(**overrides: object) -> E2EContext:
    """Build an E2EContext with defaults."""
    defaults: dict = {
        "api_url": "http://staging-api:8000",
        "frontend_url": "http://staging-frontend:3000",
        "auth_token": "test-bearer-token",
    }
    defaults.update(overrides)
    return E2EContext(**defaults)


# ---------------------------------------------------------------------------
# Test: stage_frontend_reachable
# ---------------------------------------------------------------------------


class TestStageFrontendReachable:
    """Tests for stage_frontend_reachable."""

    def test_frontend_200_html_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        resp = _mock_response(200, text="<html><body>ImpactOS</body></html>")
        resp.headers = {"content-type": "text/html; charset=utf-8"}
        client.get.return_value = resp
        ctx = _make_ctx()

        result = stage_frontend_reachable(client, ctx)

        assert result.status == "PASS"
        assert result.name == "frontend_reachable"

    def test_frontend_unreachable_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.ConnectError("Connection refused")
        ctx = _make_ctx()

        result = stage_frontend_reachable(client, ctx)

        assert result.status == "FAIL"
        assert "Cannot connect" in result.detail

    def test_frontend_500_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(500)
        ctx = _make_ctx()

        result = stage_frontend_reachable(client, ctx)

        assert result.status == "FAIL"

    def test_no_frontend_url_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(frontend_url="")

        result = stage_frontend_reachable(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_api_health
# ---------------------------------------------------------------------------


class TestStageApiHealth:
    """Tests for stage_api_health."""

    def test_all_components_healthy_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {
                "status": "healthy",
                "checks": {
                    "api": "ok",
                    "database": "ok",
                    "redis": "ok",
                    "object_storage": "ok",
                },
            },
        )
        ctx = _make_ctx()

        result = stage_api_health(client, ctx)

        assert result.status == "PASS"

    def test_missing_component_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {
                "status": "healthy",
                "checks": {
                    "api": "ok",
                    "database": "ok",
                    # Missing redis and object_storage
                },
            },
        )
        ctx = _make_ctx()

        result = stage_api_health(client, ctx)

        assert result.status == "FAIL"
        assert "Missing" in result.detail

    def test_health_503_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(503)
        ctx = _make_ctx()

        result = stage_api_health(client, ctx)

        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: stage_workspace_access
# ---------------------------------------------------------------------------


class TestStageWorkspaceAccess:
    """Tests for stage_workspace_access."""

    def test_workspace_list_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"items": [{"id": "ws-1", "name": "Test"}], "total": 1},
        )
        ctx = _make_ctx()

        result = stage_workspace_access(client, ctx)

        assert result.status == "PASS"
        assert ctx.workspace_id == "ws-1"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")

        result = stage_workspace_access(client, ctx)

        assert result.status == "SKIP"
        assert "No auth token" in result.detail

    def test_401_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(401)
        ctx = _make_ctx()

        result = stage_workspace_access(client, ctx)

        assert result.status == "FAIL"
        assert "401" in result.detail


# ---------------------------------------------------------------------------
# Test: stage_document_upload
# ---------------------------------------------------------------------------


class TestStageDocumentUpload:
    """Tests for stage_document_upload."""

    def test_no_workspace_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_document_upload(client, ctx)

        assert result.status == "SKIP"

    def test_upload_201_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            201,
            {"id": "doc-123", "filename": "test.pdf", "status": "uploaded"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_document_upload(client, ctx)

        assert result.status == "PASS"
        assert ctx.document_id == "doc-123"

    def test_upload_422_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            422, {"detail": "Validation error"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_document_upload(client, ctx)

        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: stage_copilot_reachable
# ---------------------------------------------------------------------------


class TestStageCopilotReachable:
    """Tests for stage_copilot_reachable."""

    def test_copilot_ready_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"enabled": True, "ready": True, "providers": ["anthropic"]},
        )
        ctx = _make_ctx()

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "PASS"

    def test_copilot_disabled_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"enabled": False, "ready": False, "providers": [], "detail": "No providers"},
        )
        ctx = _make_ctx()

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "SKIP"

    def test_copilot_404_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(404)
        ctx = _make_ctx()

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_scenario_run
# ---------------------------------------------------------------------------


class TestStageScenarioRun:
    """Tests for stage_scenario_run."""

    def test_no_workspace_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_scenario_run(client, ctx)

        assert result.status == "SKIP"

    def test_run_succeeds_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        # First call: list scenarios
        list_resp = _mock_response(
            200,
            {"items": [{"id": "sc-1", "name": "Test Scenario"}], "total": 1},
        )
        # Second call: trigger run
        run_resp = _mock_response(
            200,
            {"run_id": "run-abc", "status": "completed"},
        )
        client.get.return_value = list_resp
        client.post.return_value = run_resp
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_scenario_run(client, ctx)

        assert result.status == "PASS"
        assert ctx.run_id == "run-abc"


# ---------------------------------------------------------------------------
# Test: stage_governance_check
# ---------------------------------------------------------------------------


class TestStageGovernanceCheck:
    """Tests for stage_governance_check."""

    def test_no_workspace_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_governance_check(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_export_create
# ---------------------------------------------------------------------------


class TestStageExportCreate:
    """Tests for stage_export_create."""

    def test_no_run_id_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.run_id = ""

        result = stage_export_create(client, ctx)

        assert result.status == "SKIP"

    def test_export_created_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            201,
            {"export_id": "exp-1", "status": "completed"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.run_id = "run-abc"
        ctx.scenario_id = "sc-1"

        result = stage_export_create(client, ctx)

        assert result.status == "PASS"
        assert ctx.export_id == "exp-1"


# ---------------------------------------------------------------------------
# Test: stage_export_download
# ---------------------------------------------------------------------------


class TestStageExportDownload:
    """Tests for stage_export_download."""

    def test_no_export_id_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.export_id = ""

        result = stage_export_download(client, ctx)

        assert result.status == "SKIP"

    def test_download_200_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        resp = _mock_response(200, text="binary-content")
        resp.content = b"PK\x03\x04"  # ZIP magic bytes
        resp.headers = {"content-type": "application/octet-stream"}
        client.get.return_value = resp
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.export_id = "exp-1"

        result = stage_export_download(client, ctx)

        assert result.status == "PASS"
        assert "bytes" in result.detail.lower() or "download" in result.detail.lower()


# ---------------------------------------------------------------------------
# Test: run_e2e (integration / cascade)
# ---------------------------------------------------------------------------


class TestRunE2E:
    """Tests for the run_e2e orchestrator."""

    def test_report_structure(self) -> None:
        """run_e2e returns an E2EReport with correct structure."""
        ctx_manager = MagicMock()
        mock_client = MagicMock(spec=httpx.Client)
        # All calls fail with ConnectError to cascade-skip
        mock_client.get.side_effect = httpx.ConnectError("refused")
        mock_client.post.side_effect = httpx.ConnectError("refused")
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_full_e2e.httpx.Client", return_value=ctx_manager):
            report = run_e2e(
                api_url="http://localhost:9999",
                frontend_url="http://localhost:3000",
                auth_token="",
            )

        assert isinstance(report, E2EReport)
        assert report.overall in ("PASS", "FAIL")
        assert len(report.stages) > 0
        # Should have failures since everything is unreachable
        assert report.has_failures()

    def test_all_stages_represented(self) -> None:
        """All expected stage names appear in the report."""
        ctx_manager = MagicMock()
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.ConnectError("refused")
        mock_client.post.side_effect = httpx.ConnectError("refused")
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_full_e2e.httpx.Client", return_value=ctx_manager):
            report = run_e2e(
                api_url="http://localhost:9999",
                frontend_url="http://localhost:3000",
                auth_token="",
            )

        stage_names = [s.name for s in report.stages]
        expected = [
            "frontend_reachable",
            "api_health",
            "workspace_access",
            "document_upload",
            "copilot_reachable",
            "scenario_run",
            "governance_check",
            "export_create",
            "export_download",
        ]
        for name in expected:
            assert name in stage_names, f"Stage '{name}' missing from report"

    def test_report_json_serializable(self) -> None:
        """E2EReport serializes to valid JSON via asdict."""
        from dataclasses import asdict

        report = E2EReport(
            overall="FAIL",
            api_url="http://localhost:8000",
            frontend_url="http://localhost:3000",
            stages=[
                StageResult(name="test", status="FAIL", detail="test detail"),
            ],
            trace={},
        )
        data = asdict(report)
        text = json.dumps(data)
        parsed = json.loads(text)
        assert parsed["overall"] == "FAIL"
        assert len(parsed["stages"]) == 1

    def test_trace_captures_ids(self) -> None:
        """E2EReport trace dict captures IDs from context."""
        report = E2EReport(
            overall="PASS",
            api_url="http://api:8000",
            frontend_url="http://fe:3000",
            stages=[],
            trace={
                "workspace_id": "ws-1",
                "document_id": "doc-1",
                "run_id": "run-1",
                "export_id": "exp-1",
            },
        )
        assert report.trace["workspace_id"] == "ws-1"
        assert report.trace["run_id"] == "run-1"
