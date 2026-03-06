"""Tests for scripts/staging_full_e2e.py -- 14-stage full-system E2E acceptance harness.

Follows the same mock patterns as test_staging_smoke.py:
- _mock_response() builds httpx.Response mocks
- _make_ctx() builds E2EContext with defaults
- Each stage function is tested independently
- Strict mode behaviour tested via ctx.strict flag
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.staging_full_e2e import (
    E2EContext,
    E2EReport,
    StageResult,
    _JOB_POLL_INTERVAL,
    _JOB_POLL_MAX_WAIT,
    run_e2e,
    stage_api_health,
    stage_compile,
    stage_copilot_reachable,
    stage_depth_analysis,
    stage_document_upload,
    stage_export_create,
    stage_export_download,
    stage_extraction_trigger,
    stage_extraction_wait,
    stage_frontend_reachable,
    stage_governance_check,
    stage_output_validation,
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

    def test_no_frontend_url_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(frontend_url="")

        result = stage_frontend_reachable(client, ctx)

        assert result.status == "SKIP"

    def test_no_frontend_url_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(frontend_url="", strict=True)

        result = stage_frontend_reachable(client, ctx)

        assert result.status == "FAIL"
        assert "No frontend URL" in result.detail

    def test_non_html_content_type_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        resp = _mock_response(200, text='{"msg":"not html"}')
        resp.headers = {"content-type": "application/json"}
        client.get.return_value = resp
        ctx = _make_ctx()

        result = stage_frontend_reachable(client, ctx)

        assert result.status == "FAIL"
        assert "non-HTML" in result.detail


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

    def test_unhealthy_component_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {
                "status": "degraded",
                "checks": {
                    "api": "ok",
                    "database": "ok",
                    "redis": {"status": "unhealthy"},
                    "object_storage": "ok",
                },
            },
        )
        ctx = _make_ctx()

        result = stage_api_health(client, ctx)

        assert result.status == "FAIL"
        assert "Unhealthy" in result.detail

    def test_connect_error_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.ConnectError("refused")
        ctx = _make_ctx()

        result = stage_api_health(client, ctx)

        assert result.status == "FAIL"
        assert "Cannot connect" in result.detail


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

    def test_no_auth_token_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")

        result = stage_workspace_access(client, ctx)

        assert result.status == "SKIP"
        assert "No auth token" in result.detail

    def test_no_auth_token_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="", strict=True)

        result = stage_workspace_access(client, ctx)

        assert result.status == "FAIL"
        assert "No auth token" in result.detail

    def test_401_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(401)
        ctx = _make_ctx()

        result = stage_workspace_access(client, ctx)

        assert result.status == "FAIL"
        assert "401" in result.detail

    def test_403_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(403)
        ctx = _make_ctx()

        result = stage_workspace_access(client, ctx)

        assert result.status == "FAIL"
        assert "403" in result.detail

    def test_workspace_create_on_empty_list(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(200, {"items": [], "total": 0})
        client.post.return_value = _mock_response(201, {"id": "ws-new", "name": "staging-e2e-acceptance"})
        ctx = _make_ctx()

        result = stage_workspace_access(client, ctx)

        assert result.status == "PASS"
        assert ctx.workspace_id == "ws-new"
        assert "Created" in result.detail


# ---------------------------------------------------------------------------
# Test: stage_document_upload
# ---------------------------------------------------------------------------


class TestStageDocumentUpload:
    """Tests for stage_document_upload."""

    def test_no_workspace_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_document_upload(client, ctx)

        assert result.status == "SKIP"

    def test_no_workspace_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = ""

        result = stage_document_upload(client, ctx)

        assert result.status == "FAIL"

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
            422,
            {"detail": "Validation error"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_document_upload(client, ctx)

        assert result.status == "FAIL"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"

        result = stage_document_upload(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_extraction_trigger
# ---------------------------------------------------------------------------


class TestStageExtractionTrigger:
    """Tests for stage_extraction_trigger."""

    def test_extract_202_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            202,
            {"job_id": "job-ext-1", "status": "PENDING"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.document_id = "doc-1"

        result = stage_extraction_trigger(client, ctx)

        assert result.status == "PASS"
        assert ctx.extraction_job_id == "job-ext-1"
        assert "job_id=job-ext-1" in result.detail

    def test_no_document_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.document_id = ""

        result = stage_extraction_trigger(client, ctx)

        assert result.status == "SKIP"

    def test_no_document_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = "ws-1"
        ctx.document_id = ""

        result = stage_extraction_trigger(client, ctx)

        assert result.status == "FAIL"

    def test_no_workspace_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""
        ctx.document_id = "doc-1"

        result = stage_extraction_trigger(client, ctx)

        assert result.status == "SKIP"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"
        ctx.document_id = "doc-1"

        result = stage_extraction_trigger(client, ctx)

        assert result.status == "SKIP"

    def test_server_error_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(500, text="Internal server error")
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.document_id = "doc-1"

        result = stage_extraction_trigger(client, ctx)

        assert result.status == "FAIL"
        assert "500" in result.detail

    def test_connect_error_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.side_effect = httpx.ConnectError("refused")
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.document_id = "doc-1"

        result = stage_extraction_trigger(client, ctx)

        assert result.status == "FAIL"
        assert "Error" in result.detail


# ---------------------------------------------------------------------------
# Test: stage_extraction_wait
# ---------------------------------------------------------------------------


class TestStageExtractionWait:
    """Tests for stage_extraction_wait (worker execution proof)."""

    def test_immediate_completed_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"job_id": "job-1", "status": "COMPLETED"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.extraction_job_id = "job-1"

        result = stage_extraction_wait(client, ctx)

        assert result.status == "PASS"
        assert "worker executed" in result.detail.lower()

    def test_job_failed_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"job_id": "job-1", "status": "FAILED", "error_message": "Provider timeout"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.extraction_job_id = "job-1"

        result = stage_extraction_wait(client, ctx)

        assert result.status == "FAIL"
        assert "Provider timeout" in result.detail

    @patch("scripts.staging_full_e2e.time.sleep")
    def test_poll_then_completed(self, mock_sleep: MagicMock) -> None:
        """Simulate PENDING → PROCESSING → COMPLETED."""
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = [
            _mock_response(200, {"job_id": "job-1", "status": "PENDING"}),
            _mock_response(200, {"job_id": "job-1", "status": "PROCESSING"}),
            _mock_response(200, {"job_id": "job-1", "status": "COMPLETED"}),
        ]
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.extraction_job_id = "job-1"

        result = stage_extraction_wait(client, ctx)

        assert result.status == "PASS"
        assert mock_sleep.call_count == 2

    @patch("scripts.staging_full_e2e.time.sleep")
    @patch("scripts.staging_full_e2e._JOB_POLL_MAX_WAIT", 4.0)
    @patch("scripts.staging_full_e2e._JOB_POLL_INTERVAL", 2.0)
    def test_timeout_fails(self, mock_sleep: MagicMock) -> None:
        """Simulate never-completing job."""
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"job_id": "job-1", "status": "PENDING"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.extraction_job_id = "job-1"

        result = stage_extraction_wait(client, ctx)

        assert result.status == "FAIL"
        assert "timed out" in result.detail.lower()

    def test_no_job_id_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.extraction_job_id = ""

        result = stage_extraction_wait(client, ctx)

        assert result.status == "SKIP"

    def test_no_job_id_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = "ws-1"
        ctx.extraction_job_id = ""

        result = stage_extraction_wait(client, ctx)

        assert result.status == "FAIL"

    def test_status_endpoint_error_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(500)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.extraction_job_id = "job-1"

        result = stage_extraction_wait(client, ctx)

        assert result.status == "FAIL"
        assert "500" in result.detail


# ---------------------------------------------------------------------------
# Test: stage_compile
# ---------------------------------------------------------------------------


class TestStageCompile:
    """Tests for stage_compile (LLM-backed sector mapping)."""

    def test_compile_201_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            201,
            {
                "compilation_id": "comp-1",
                "high_confidence": 5,
                "medium_confidence": 2,
                "low_confidence": 1,
            },
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.document_id = "doc-1"

        result = stage_compile(client, ctx)

        assert result.status == "PASS"
        assert ctx.compilation_id == "comp-1"
        assert "H=5" in result.detail

    def test_compile_503_provider_unavailable_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        resp = _mock_response(503, text="No LLM provider configured")
        client.post.return_value = resp
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_compile(client, ctx)

        assert result.status == "FAIL"
        assert "503" in result.detail

    def test_no_workspace_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_compile(client, ctx)

        assert result.status == "SKIP"

    def test_no_workspace_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = ""

        result = stage_compile(client, ctx)

        assert result.status == "FAIL"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"

        result = stage_compile(client, ctx)

        assert result.status == "SKIP"

    def test_compile_uses_document_id(self) -> None:
        """When document_id is set, compile payload includes it."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            200,
            {"compilation_id": "comp-2", "high_confidence": 3, "medium_confidence": 1, "low_confidence": 0},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.document_id = "doc-1"

        result = stage_compile(client, ctx)

        assert result.status == "PASS"
        # Verify the post was called
        call_args = client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("document_id") == "doc-1"


# ---------------------------------------------------------------------------
# Test: stage_depth_analysis
# ---------------------------------------------------------------------------


class TestStageDepthAnalysis:
    """Tests for stage_depth_analysis (LLM-backed depth engine)."""

    def test_depth_201_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            201,
            {"plan_id": "depth-1", "status": "created"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_depth_analysis(client, ctx)

        assert result.status == "PASS"
        assert ctx.depth_plan_id == "depth-1"

    def test_depth_503_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        resp = _mock_response(503, text="No LLM provider configured")
        client.post.return_value = resp
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_depth_analysis(client, ctx)

        assert result.status == "FAIL"
        assert "503" in result.detail

    def test_no_workspace_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_depth_analysis(client, ctx)

        assert result.status == "SKIP"

    def test_no_workspace_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = ""

        result = stage_depth_analysis(client, ctx)

        assert result.status == "FAIL"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"

        result = stage_depth_analysis(client, ctx)

        assert result.status == "SKIP"

    def test_depth_with_scenario_id(self) -> None:
        """When scenario_id is set, depth payload includes it."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _mock_response(
            201,
            {"plan_id": "depth-2", "status": "created"},
        )
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.scenario_id = "sc-1"

        result = stage_depth_analysis(client, ctx)

        assert result.status == "PASS"
        call_args = client.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert payload.get("scenario_spec_id") == "sc-1"

    def test_connect_error_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.side_effect = httpx.ConnectError("refused")
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_depth_analysis(client, ctx)

        assert result.status == "FAIL"
        assert "Error" in result.detail


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

    def test_copilot_disabled_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"enabled": False, "ready": False, "providers": [], "detail": "No providers"},
        )
        ctx = _make_ctx()

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "SKIP"

    def test_copilot_disabled_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"enabled": False, "ready": False, "providers": [], "detail": "No providers"},
        )
        ctx = _make_ctx(strict=True)

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "FAIL"

    def test_copilot_404_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(404)
        ctx = _make_ctx()

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "SKIP"

    def test_copilot_404_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(404)
        ctx = _make_ctx(strict=True)

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "FAIL"

    def test_copilot_500_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(500)
        ctx = _make_ctx()

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "FAIL"

    def test_copilot_enabled_not_ready_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            200,
            {"enabled": True, "ready": False, "providers": [], "detail": "Provider initializing"},
        )
        ctx = _make_ctx()

        result = stage_copilot_reachable(client, ctx)

        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: stage_scenario_run
# ---------------------------------------------------------------------------


class TestStageScenarioRun:
    """Tests for stage_scenario_run."""

    def test_no_workspace_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_scenario_run(client, ctx)

        assert result.status == "SKIP"

    def test_no_workspace_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = ""

        result = stage_scenario_run(client, ctx)

        assert result.status == "FAIL"

    def test_run_succeeds_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        # List scenarios
        list_resp = _mock_response(
            200,
            {"items": [{"id": "sc-1", "name": "Test Scenario"}], "total": 1},
        )
        # Run scenario
        run_resp = _mock_response(
            200,
            {
                "run_id": "run-abc",
                "status": "completed",
                "result_sets": [
                    {"metric_type": "output", "values": {"sector_1": 1500.0}},
                ],
            },
        )
        client.get.return_value = list_resp
        client.post.return_value = run_resp
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_scenario_run(client, ctx)

        assert result.status == "PASS"
        assert ctx.run_id == "run-abc"
        assert ctx.scenario_id == "sc-1"
        assert len(ctx.run_result_sets) == 1

    def test_no_scenarios_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(200, {"items": [], "total": 0})
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_scenario_run(client, ctx)

        assert result.status == "SKIP"

    def test_no_scenarios_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(200, {"items": [], "total": 0})
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = "ws-1"

        result = stage_scenario_run(client, ctx)

        assert result.status == "FAIL"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"

        result = stage_scenario_run(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_governance_check
# ---------------------------------------------------------------------------


class TestStageGovernanceCheck:
    """Tests for stage_governance_check."""

    def test_no_workspace_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""

        result = stage_governance_check(client, ctx)

        assert result.status == "SKIP"

    def test_no_workspace_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = ""

        result = stage_governance_check(client, ctx)

        assert result.status == "FAIL"

    def test_governance_200_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(200, {"items": [], "total": 0})
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_governance_check(client, ctx)

        assert result.status == "PASS"

    def test_governance_404_passes(self) -> None:
        """404 = no claims yet, but governance layer is reachable."""
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(404)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_governance_check(client, ctx)

        assert result.status == "PASS"

    def test_governance_401_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(401)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"

        result = stage_governance_check(client, ctx)

        assert result.status == "FAIL"
        assert "401" in result.detail

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"

        result = stage_governance_check(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_export_create
# ---------------------------------------------------------------------------


class TestStageExportCreate:
    """Tests for stage_export_create."""

    def test_no_run_id_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.run_id = ""

        result = stage_export_create(client, ctx)

        assert result.status == "SKIP"

    def test_no_run_id_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = "ws-1"
        ctx.run_id = ""

        result = stage_export_create(client, ctx)

        assert result.status == "FAIL"

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

    def test_no_workspace_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""
        ctx.run_id = "run-1"

        result = stage_export_create(client, ctx)

        assert result.status == "SKIP"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"
        ctx.run_id = "run-1"

        result = stage_export_create(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_export_download
# ---------------------------------------------------------------------------


class TestStageExportDownload:
    """Tests for stage_export_download."""

    def test_no_export_id_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.export_id = ""

        result = stage_export_download(client, ctx)

        assert result.status == "SKIP"

    def test_no_export_id_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.workspace_id = "ws-1"
        ctx.export_id = ""

        result = stage_export_download(client, ctx)

        assert result.status == "FAIL"

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

    def test_download_empty_content_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        resp = _mock_response(200)
        resp.content = b""
        client.get.return_value = resp
        ctx = _make_ctx()
        ctx.workspace_id = "ws-1"
        ctx.export_id = "exp-1"

        result = stage_export_download(client, ctx)

        assert result.status == "FAIL"
        assert "empty" in result.detail.lower()

    def test_no_workspace_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.workspace_id = ""
        ctx.export_id = "exp-1"

        result = stage_export_download(client, ctx)

        assert result.status == "SKIP"

    def test_no_auth_token_skips(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(auth_token="")
        ctx.workspace_id = "ws-1"
        ctx.export_id = "exp-1"

        result = stage_export_download(client, ctx)

        assert result.status == "SKIP"


# ---------------------------------------------------------------------------
# Test: stage_output_validation
# ---------------------------------------------------------------------------


class TestStageOutputValidation:
    """Tests for stage_output_validation."""

    def test_no_run_id_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.run_id = ""

        result = stage_output_validation(client, ctx)

        assert result.status == "SKIP"

    def test_no_run_id_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.run_id = ""

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"

    def test_no_result_sets_skips_default(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.run_id = "run-1"
        ctx.run_result_sets = []

        result = stage_output_validation(client, ctx)

        assert result.status == "SKIP"

    def test_no_result_sets_fails_strict(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx(strict=True)
        ctx.run_id = "run-1"
        ctx.run_result_sets = []

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"

    def test_valid_results_passes(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"sector_1": 1500.0, "sector_2": 2300.0}},
            {"metric_type": "employment", "values": {"sector_1": 45.0, "sector_2": 67.0}},
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "PASS"
        assert "2 result_sets" in result.detail

    def test_missing_metric_type_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"values": {"sector_1": 100.0}},  # Missing metric_type
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"
        assert "missing metric_type" in result.detail

    def test_empty_values_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {}},
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"
        assert "empty values" in result.detail

    def test_all_zero_values_fails(self) -> None:
        client = MagicMock(spec=httpx.Client)
        ctx = _make_ctx()
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"sector_1": 0, "sector_2": 0.0}},
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"
        assert "zero" in result.detail.lower()

    def test_validate_outputs_persisted_match_passes(self) -> None:
        """With --validate-outputs, fetches persisted run and compares."""
        client = MagicMock(spec=httpx.Client)
        persisted_data = {
            "run_id": "run-1",
            "result_sets": [
                {"metric_type": "output", "values": {"sector_1": 1500.0}},
            ],
        }
        client.get.return_value = _mock_response(200, persisted_data)
        ctx = _make_ctx(validate_outputs=True)
        ctx.workspace_id = "ws-1"
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"sector_1": 1500.0}},
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "PASS"
        assert "persisted data matches" in result.detail

    def test_validate_outputs_count_mismatch_fails(self) -> None:
        """Persisted result_sets count differs from in-memory."""
        client = MagicMock(spec=httpx.Client)
        persisted_data = {
            "run_id": "run-1",
            "result_sets": [
                {"metric_type": "output", "values": {"sector_1": 1500.0}},
                {"metric_type": "employment", "values": {"sector_1": 45.0}},
            ],
        }
        client.get.return_value = _mock_response(200, persisted_data)
        ctx = _make_ctx(validate_outputs=True)
        ctx.workspace_id = "ws-1"
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"sector_1": 1500.0}},
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"
        assert "count" in result.detail.lower() or "Persisted" in result.detail

    def test_validate_outputs_type_mismatch_fails(self) -> None:
        """Persisted metric types differ from in-memory."""
        client = MagicMock(spec=httpx.Client)
        persisted_data = {
            "run_id": "run-1",
            "result_sets": [
                {"metric_type": "employment", "values": {"sector_1": 45.0}},
            ],
        }
        client.get.return_value = _mock_response(200, persisted_data)
        ctx = _make_ctx(validate_outputs=True)
        ctx.workspace_id = "ws-1"
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"sector_1": 1500.0}},
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"
        assert "mismatch" in result.detail.lower() or "Metric type" in result.detail

    def test_validate_outputs_fetch_fails(self) -> None:
        """Persisted run fetch returns error."""
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(500)
        ctx = _make_ctx(validate_outputs=True)
        ctx.workspace_id = "ws-1"
        ctx.run_id = "run-1"
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"sector_1": 1500.0}},
        ]

        result = stage_output_validation(client, ctx)

        assert result.status == "FAIL"
        assert "fetch" in result.detail.lower() or "500" in result.detail


# ---------------------------------------------------------------------------
# Test: E2EContext._missing (strict vs default)
# ---------------------------------------------------------------------------


class TestE2EContextMissing:
    """Tests for E2EContext._missing strict/default behaviour."""

    def test_missing_returns_skip_by_default(self) -> None:
        ctx = _make_ctx()
        result = ctx._missing("test_stage", "No prerequisite")
        assert result.status == "SKIP"
        assert result.name == "test_stage"

    def test_missing_returns_fail_in_strict(self) -> None:
        ctx = _make_ctx(strict=True)
        result = ctx._missing("test_stage", "No prerequisite")
        assert result.status == "FAIL"
        assert result.name == "test_stage"
        assert "No prerequisite" in result.detail


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

    def test_all_14_stages_represented(self) -> None:
        """All 14 expected stage names appear in the report."""
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
            "extraction_trigger",
            "extraction_wait",
            "compile",
            "depth_analysis",
            "copilot_reachable",
            "scenario_run",
            "governance_check",
            "export_create",
            "export_download",
            "output_validation",
        ]
        assert len(expected) == 14
        for name in expected:
            assert name in stage_names, f"Stage '{name}' missing from report"

    def test_cascade_skip_on_api_failure(self) -> None:
        """When API health fails, all downstream stages get SKIP (default mode)."""
        ctx_manager = MagicMock()
        mock_client = MagicMock(spec=httpx.Client)
        # Frontend succeeds
        fe_resp = _mock_response(200, text="<html>ImpactOS</html>")
        fe_resp.headers = {"content-type": "text/html; charset=utf-8"}
        # API returns 503
        api_resp = _mock_response(503)

        def get_side_effect(url, **kwargs):
            if "localhost:3000" in url:
                return fe_resp
            return api_resp

        mock_client.get.side_effect = get_side_effect
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_full_e2e.httpx.Client", return_value=ctx_manager):
            report = run_e2e(
                api_url="http://localhost:9999",
                frontend_url="http://localhost:3000",
                auth_token="tok",
            )

        # Frontend should PASS, API should FAIL, rest SKIP
        by_name = {s.name: s for s in report.stages}
        assert by_name["frontend_reachable"].status == "PASS"
        assert by_name["api_health"].status == "FAIL"
        assert by_name["workspace_access"].status == "SKIP"
        assert by_name["extraction_trigger"].status == "SKIP"
        assert by_name["output_validation"].status == "SKIP"

    def test_cascade_fail_on_api_failure_strict(self) -> None:
        """In strict mode, cascade produces FAIL not SKIP."""
        ctx_manager = MagicMock()
        mock_client = MagicMock(spec=httpx.Client)
        fe_resp = _mock_response(200, text="<html>ImpactOS</html>")
        fe_resp.headers = {"content-type": "text/html; charset=utf-8"}
        api_resp = _mock_response(503)

        def get_side_effect(url, **kwargs):
            if "localhost:3000" in url:
                return fe_resp
            return api_resp

        mock_client.get.side_effect = get_side_effect
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_full_e2e.httpx.Client", return_value=ctx_manager):
            report = run_e2e(
                api_url="http://localhost:9999",
                frontend_url="http://localhost:3000",
                auth_token="tok",
                strict=True,
            )

        by_name = {s.name: s for s in report.stages}
        assert by_name["api_health"].status == "FAIL"
        # In strict mode, cascade-skip becomes cascade-FAIL
        assert by_name["workspace_access"].status == "FAIL"
        assert by_name["extraction_trigger"].status == "FAIL"
        assert by_name["output_validation"].status == "FAIL"
        assert report.overall == "FAIL"

    def test_report_json_serializable(self) -> None:
        """E2EReport serializes to valid JSON via asdict."""
        report = E2EReport(
            overall="FAIL",
            api_url="http://localhost:8000",
            frontend_url="http://localhost:3000",
            strict=True,
            stages=[
                StageResult(name="test", status="FAIL", detail="test detail"),
            ],
            trace={},
        )
        data = asdict(report)
        text = json.dumps(data)
        parsed = json.loads(text)
        assert parsed["overall"] == "FAIL"
        assert parsed["strict"] is True
        assert len(parsed["stages"]) == 1

    def test_trace_captures_all_ids(self) -> None:
        """E2EReport trace dict captures all context IDs."""
        report = E2EReport(
            overall="PASS",
            api_url="http://api:8000",
            frontend_url="http://fe:3000",
            stages=[],
            trace={
                "workspace_id": "ws-1",
                "document_id": "doc-1",
                "extraction_job_id": "job-1",
                "compilation_id": "comp-1",
                "depth_plan_id": "depth-1",
                "scenario_id": "sc-1",
                "run_id": "run-1",
                "export_id": "exp-1",
            },
        )
        assert report.trace["workspace_id"] == "ws-1"
        assert report.trace["extraction_job_id"] == "job-1"
        assert report.trace["compilation_id"] == "comp-1"
        assert report.trace["depth_plan_id"] == "depth-1"
        assert report.trace["run_id"] == "run-1"

    def test_strict_overall_fail_on_skips(self) -> None:
        """In strict mode, any SKIP produces overall FAIL."""
        ctx_manager = MagicMock()
        mock_client = MagicMock(spec=httpx.Client)
        # API healthy, but no auth token → stages return SKIP/FAIL
        health_resp = _mock_response(
            200,
            {"status": "healthy", "checks": {"api": "ok", "database": "ok", "redis": "ok", "object_storage": "ok"}},
        )
        fe_resp = _mock_response(200, text="<html>OK</html>")
        fe_resp.headers = {"content-type": "text/html"}

        def get_side_effect(url, **kwargs):
            if "3000" in url:
                return fe_resp
            if "/health" in url:
                return health_resp
            # Other GETs return 200 with minimal body
            return _mock_response(200, {"items": [], "total": 0})

        mock_client.get.side_effect = get_side_effect
        mock_client.post.return_value = _mock_response(200, {})
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_full_e2e.httpx.Client", return_value=ctx_manager):
            report = run_e2e(
                api_url="http://localhost:9999",
                frontend_url="http://localhost:3000",
                auth_token="",  # No token — will cause SKIPs
                strict=True,
            )

        # In strict mode, SKIPs count as failures
        assert report.overall == "FAIL"
        assert report.strict is True

    def test_report_has_strict_flag(self) -> None:
        """E2EReport records the strict flag."""
        ctx_manager = MagicMock()
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.ConnectError("refused")
        mock_client.post.side_effect = httpx.ConnectError("refused")
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_full_e2e.httpx.Client", return_value=ctx_manager):
            report = run_e2e(
                api_url="http://localhost:9999",
                strict=True,
            )

        assert report.strict is True
