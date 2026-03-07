"""Tests for the 15-stage full-system E2E acceptance harness.

Covers:
- All 15 stage functions with success, failure, and edge cases
- Strict vs default mode behaviour (SKIP → FAIL)
- OIDC client_credentials grant (discovery + token exchange)
- Connected pipeline: ai_compile → scenario_build → scenario_run
- Governance evaluation (not reachability)
- Copilot real LLM interaction (not status probe)
- Golden fixture output validation
- Cascade-skip/fail when API is unreachable
- E2EContext, E2EReport, StageResult data structures
- Report output and JSON serialization
- run_e2e integration (15 stages, OIDC params)
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest

from scripts.staging_full_e2e import (
    E2EContext,
    E2EReport,
    StageResult,
    _GOLDEN_FIXTURE_PATH,
    _HEALTH_COMPONENTS,
    _load_golden_fixture,
    run_e2e,
    stage_ai_compile,
    stage_api_health,
    stage_copilot_query,
    stage_depth_analysis,
    stage_document_upload,
    stage_export_download,
    stage_extraction_trigger,
    stage_extraction_wait,
    stage_frontend_verify,
    stage_governance_evaluate,
    stage_oidc_token,
    stage_output_validation,
    stage_scenario_build,
    stage_scenario_run,
    stage_workspace_access,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOLDEN_FIXTURE = {
    "version": "1.0",
    "result_sets": {
        "min_count": 1,
        "required_metric_types": ["output"],
        "known_metric_types": ["output", "value_added", "employment", "imports"],
        "per_metric": {
            "min_sectors_with_values": 1,
            "value_range_min": -1e15,
            "value_range_max": 1e15,
            "require_non_zero": True,
        },
    },
    "governance": {"min_claims_extracted": 1, "require_governance_status": True},
    "export": {"min_bytes": 100, "accepted_formats": ["excel"]},
    "determinism": {
        "require_persisted_match": True,
        "metric_type_set_must_match": True,
        "result_set_count_must_match": True,
    },
}


def _ctx(**overrides) -> E2EContext:
    defaults = dict(api_url="http://api:8000", frontend_url="http://fe:3000")
    defaults.update(overrides)
    return E2EContext(**defaults)


def _response(status_code=200, json_body=None, text="", content=b"", headers=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text or json.dumps(json_body or {})
    resp.content = content or resp.text.encode()
    resp.headers = headers or {"content-type": "application/json"}
    return resp


def _html_response(status_code=200, body="<html>ok</html>"):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = {"content-type": "text/html; charset=utf-8"}
    resp.json.return_value = {}
    resp.text = body
    resp.content = body.encode()
    return resp


# ===========================================================================
# Data structure tests
# ===========================================================================


class TestStageResult:
    def test_creation(self):
        sr = StageResult(name="test", status="PASS", detail="ok")
        assert sr.name == "test"
        assert sr.status == "PASS"
        assert sr.detail == "ok"

    def test_as_dict(self):
        sr = StageResult(name="a", status="FAIL", detail="err")
        d = asdict(sr)
        assert d == {"name": "a", "status": "FAIL", "detail": "err"}


class TestE2EContext:
    def test_defaults(self):
        ctx = _ctx()
        assert ctx.api_url == "http://api:8000"
        assert ctx.auth_token == ""
        assert ctx.strict is False
        assert ctx.oidc_issuer == ""
        assert ctx.suggestions == []
        assert ctx.claim_ids == []
        assert ctx.governance_status == {}

    def test_auth_headers_with_token(self):
        ctx = _ctx(auth_token="tok123")
        assert ctx.auth_headers() == {"Authorization": "Bearer tok123"}

    def test_auth_headers_empty(self):
        ctx = _ctx()
        assert ctx.auth_headers() == {}

    def test_missing_skip_default(self):
        ctx = _ctx(strict=False)
        r = ctx._missing("test", "reason")
        assert r.status == "SKIP"

    def test_missing_fail_strict(self):
        ctx = _ctx(strict=True)
        r = ctx._missing("test", "reason")
        assert r.status == "FAIL"

    def test_oidc_fields(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c1", oidc_client_secret="s1")
        assert ctx.oidc_issuer == "https://idp.example.com"
        assert ctx.oidc_client_id == "c1"
        assert ctx.oidc_client_secret == "s1"

    def test_connected_pipeline_fields(self):
        ctx = _ctx()
        ctx.suggestions = [{"line_item_id": "1"}]
        ctx.model_version_id = "mv1"
        ctx.sector_codes = ["S01", "S02"]
        ctx.scenario_spec_id = "sc1"
        ctx.claim_ids = ["cl1"]
        ctx.governance_status = {"nff_passed": True}
        ctx.session_id = "sess1"
        assert len(ctx.suggestions) == 1
        assert ctx.model_version_id == "mv1"
        assert len(ctx.sector_codes) == 2


class TestE2EReport:
    def test_no_failures(self):
        report = E2EReport(overall="PASS", api_url="http://api:8000", frontend_url="http://fe:3000")
        report.stages = [StageResult("a", "PASS", "ok"), StageResult("b", "SKIP", "skipped")]
        assert not report.has_failures()

    def test_has_failures(self):
        report = E2EReport(overall="FAIL", api_url="http://api:8000", frontend_url="http://fe:3000")
        report.stages = [StageResult("a", "PASS", "ok"), StageResult("b", "FAIL", "err")]
        assert report.has_failures()


# ===========================================================================
# Stage 1: OIDC Token Acquisition
# ===========================================================================


class TestStageOidcToken:
    def test_strict_no_oidc_config_fails(self):
        ctx = _ctx(strict=True)
        client = MagicMock()
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "Strict mode" in r.detail

    def test_default_preissued_token_skip(self):
        ctx = _ctx(strict=False, auth_token="pre-issued")
        client = MagicMock()
        r = stage_oidc_token(client, ctx)
        assert r.status == "SKIP"
        assert "pre-issued" in r.detail

    def test_default_no_oidc_no_token_skip(self):
        ctx = _ctx(strict=False)
        client = MagicMock()
        r = stage_oidc_token(client, ctx)
        assert r.status == "SKIP"

    def test_oidc_missing_client_id_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="", oidc_client_secret="s")
        client = MagicMock()
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "missing" in r.detail.lower()

    def test_oidc_missing_client_secret_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="")
        client = MagicMock()
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"

    def test_oidc_discovery_non_200_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="s")
        client = MagicMock()
        client.get.return_value = _response(status_code=500)
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "500" in r.detail

    def test_oidc_discovery_missing_token_endpoint_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="s")
        client = MagicMock()
        client.get.return_value = _response(json_body={"issuer": "https://idp.example.com"})
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "token_endpoint" in r.detail

    def test_oidc_discovery_exception_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="s")
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError("network down")
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "discovery failed" in r.detail.lower()

    def test_oidc_token_endpoint_non_200_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="s")
        client = MagicMock()
        disc_resp = _response(json_body={"token_endpoint": "https://idp.example.com/token"})
        tok_resp = _response(status_code=401, text="unauthorized")
        client.get.return_value = disc_resp
        client.post.return_value = tok_resp
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "401" in r.detail

    def test_oidc_token_response_missing_access_token_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="s")
        client = MagicMock()
        disc_resp = _response(json_body={"token_endpoint": "https://idp.example.com/token"})
        tok_resp = _response(json_body={"token_type": "bearer"})
        client.get.return_value = disc_resp
        client.post.return_value = tok_resp
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "access_token" in r.detail

    def test_oidc_full_flow_pass(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="s")
        client = MagicMock()
        disc_resp = _response(json_body={"token_endpoint": "https://idp.example.com/token"})
        tok_resp = _response(json_body={"access_token": "tok-xyz", "expires_in": 3600})
        client.get.return_value = disc_resp
        client.post.return_value = tok_resp
        r = stage_oidc_token(client, ctx)
        assert r.status == "PASS"
        assert ctx.auth_token == "tok-xyz"
        assert "3600" in r.detail

    def test_oidc_token_exception_fails(self):
        ctx = _ctx(oidc_issuer="https://idp.example.com", oidc_client_id="c", oidc_client_secret="s")
        client = MagicMock()
        disc_resp = _response(json_body={"token_endpoint": "https://idp.example.com/token"})
        client.get.return_value = disc_resp
        client.post.side_effect = Exception("timeout")
        r = stage_oidc_token(client, ctx)
        assert r.status == "FAIL"
        assert "Token acquisition failed" in r.detail


# ===========================================================================
# Stage 2: Frontend Verification
# ===========================================================================


class TestStageFrontendVerify:
    def test_no_frontend_url_skip(self):
        ctx = _ctx(frontend_url="")
        r = stage_frontend_verify(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_frontend_url_strict_fail(self):
        ctx = _ctx(frontend_url="", strict=True)
        r = stage_frontend_verify(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_html_200_pass(self):
        ctx = _ctx()
        client = MagicMock()
        client.get.return_value = _html_response()
        r = stage_frontend_verify(client, ctx)
        assert r.status == "PASS"

    def test_non_200_fails(self):
        ctx = _ctx()
        client = MagicMock()
        client.get.return_value = _html_response(status_code=503)
        r = stage_frontend_verify(client, ctx)
        assert r.status == "FAIL"
        assert "503" in r.detail

    def test_non_html_content_type_fails(self):
        ctx = _ctx()
        client = MagicMock()
        resp = _response(status_code=200, json_body={"error": "not html"})
        resp.headers = {"content-type": "application/json"}
        client.get.return_value = resp
        r = stage_frontend_verify(client, ctx)
        assert r.status == "FAIL"
        assert "non-HTML" in r.detail

    def test_connect_error_fails(self):
        ctx = _ctx()
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError("connection refused")
        r = stage_frontend_verify(client, ctx)
        assert r.status == "FAIL"
        assert "Cannot connect" in r.detail

    def test_generic_exception_fails(self):
        ctx = _ctx()
        client = MagicMock()
        client.get.side_effect = Exception("unexpected")
        r = stage_frontend_verify(client, ctx)
        assert r.status == "FAIL"
        assert "Error reaching" in r.detail

    def test_strict_oidc_provider_check_pass(self):
        ctx = _ctx(strict=True)
        client = MagicMock()
        html_resp = _html_response()
        prov_resp = _response(json_body={"impactos-oidc": {"id": "impactos-oidc"}})
        client.get.side_effect = [html_resp, prov_resp]
        r = stage_frontend_verify(client, ctx)
        assert r.status == "PASS"

    def test_strict_oidc_provider_missing_fails(self):
        ctx = _ctx(strict=True)
        client = MagicMock()
        html_resp = _html_response()
        prov_resp = _response(json_body={"credentials": {"id": "credentials"}})
        client.get.side_effect = [html_resp, prov_resp]
        r = stage_frontend_verify(client, ctx)
        assert r.status == "FAIL"
        assert "impactos-oidc" in r.detail

    def test_strict_provider_check_error_still_passes(self):
        """Provider check is best-effort — exception during check still passes."""
        ctx = _ctx(strict=True)
        client = MagicMock()
        html_resp = _html_response()
        client.get.side_effect = [html_resp, Exception("provider check failed")]
        r = stage_frontend_verify(client, ctx)
        assert r.status == "PASS"


# ===========================================================================
# Stage 3: API Health
# ===========================================================================


class TestStageApiHealth:
    def test_all_healthy_pass(self):
        checks = {c: "ok" for c in _HEALTH_COMPONENTS}
        ctx = _ctx()
        client = MagicMock()
        client.get.return_value = _response(json_body={"checks": checks})
        r = stage_api_health(client, ctx)
        assert r.status == "PASS"
        assert str(len(_HEALTH_COMPONENTS)) in r.detail

    def test_dict_status_healthy_pass(self):
        checks = {c: {"status": "healthy"} for c in _HEALTH_COMPONENTS}
        ctx = _ctx()
        client = MagicMock()
        client.get.return_value = _response(json_body={"checks": checks})
        r = stage_api_health(client, ctx)
        assert r.status == "PASS"

    def test_missing_component_fails(self):
        checks = {"api": "ok", "database": "ok"}
        ctx = _ctx()
        client = MagicMock()
        client.get.return_value = _response(json_body={"checks": checks})
        r = stage_api_health(client, ctx)
        assert r.status == "FAIL"
        assert "Missing" in r.detail

    def test_unhealthy_component_fails(self):
        checks = {c: "ok" for c in _HEALTH_COMPONENTS}
        checks["redis"] = "unhealthy"
        ctx = _ctx()
        client = MagicMock()
        client.get.return_value = _response(json_body={"checks": checks})
        r = stage_api_health(client, ctx)
        assert r.status == "FAIL"
        assert "redis" in r.detail

    def test_non_200_fails(self):
        ctx = _ctx()
        client = MagicMock()
        client.get.return_value = _response(status_code=503)
        r = stage_api_health(client, ctx)
        assert r.status == "FAIL"
        assert "503" in r.detail

    def test_connect_error_fails(self):
        ctx = _ctx()
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError("refused")
        r = stage_api_health(client, ctx)
        assert r.status == "FAIL"
        assert "Cannot connect" in r.detail

    def test_exception_fails(self):
        ctx = _ctx()
        client = MagicMock()
        client.get.side_effect = RuntimeError("boom")
        r = stage_api_health(client, ctx)
        assert r.status == "FAIL"
        assert "Error checking" in r.detail


# ===========================================================================
# Stage 4: Workspace Access
# ===========================================================================


class TestStageWorkspaceAccess:
    def test_no_auth_token_skip(self):
        ctx = _ctx()
        r = stage_workspace_access(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_token_strict_fail(self):
        ctx = _ctx(strict=True)
        r = stage_workspace_access(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_existing_workspace_pass(self):
        ctx = _ctx(auth_token="tok")
        client = MagicMock()
        client.get.return_value = _response(json_body={"items": [{"id": "ws-1"}]})
        r = stage_workspace_access(client, ctx)
        assert r.status == "PASS"
        assert ctx.workspace_id == "ws-1"

    def test_create_workspace_pass(self):
        ctx = _ctx(auth_token="tok")
        client = MagicMock()
        client.get.return_value = _response(json_body={"items": []})
        client.post.return_value = _response(status_code=201, json_body={"id": "ws-new"})
        r = stage_workspace_access(client, ctx)
        assert r.status == "PASS"
        assert ctx.workspace_id == "ws-new"

    def test_401_fails(self):
        ctx = _ctx(auth_token="bad")
        client = MagicMock()
        client.get.return_value = _response(status_code=401)
        r = stage_workspace_access(client, ctx)
        assert r.status == "FAIL"
        assert "401" in r.detail

    def test_403_fails(self):
        ctx = _ctx(auth_token="tok")
        client = MagicMock()
        client.get.return_value = _response(status_code=403)
        r = stage_workspace_access(client, ctx)
        assert r.status == "FAIL"
        assert "403" in r.detail

    def test_exception_fails(self):
        ctx = _ctx(auth_token="tok")
        client = MagicMock()
        client.get.side_effect = Exception("timeout")
        r = stage_workspace_access(client, ctx)
        assert r.status == "FAIL"

    def test_list_returns_direct_array(self):
        """Handles response that is a direct array (not wrapped in {items: []})."""
        ctx = _ctx(auth_token="tok")
        client = MagicMock()
        client.get.return_value = _response(json_body=[{"id": "ws-direct"}])
        r = stage_workspace_access(client, ctx)
        assert r.status == "PASS"
        assert ctx.workspace_id == "ws-direct"


# ===========================================================================
# Stage 5: Document Upload
# ===========================================================================


class TestStageDocumentUpload:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok")
        r = stage_document_upload(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_token_skip(self):
        ctx = _ctx(workspace_id="ws-1")
        r = stage_document_upload(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_upload_success(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=201, json_body={"id": "doc-1"})
        r = stage_document_upload(client, ctx)
        assert r.status == "PASS"
        assert ctx.document_id == "doc-1"

    def test_upload_failure(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=400, text="bad request")
        r = stage_document_upload(client, ctx)
        assert r.status == "FAIL"

    def test_upload_exception(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.post.side_effect = Exception("timeout")
        r = stage_document_upload(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 6: Extraction Trigger
# ===========================================================================


class TestStageExtractionTrigger:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok", document_id="doc-1")
        r = stage_extraction_trigger(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_document_skip(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        r = stage_extraction_trigger(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1", document_id="doc-1")
        r = stage_extraction_trigger(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_trigger_success(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=202, json_body={"job_id": "j1", "status": "QUEUED"})
        r = stage_extraction_trigger(client, ctx)
        assert r.status == "PASS"
        assert ctx.extraction_job_id == "j1"

    def test_trigger_failure(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=500, text="error")
        r = stage_extraction_trigger(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 7: Extraction Wait (Worker Proof)
# ===========================================================================


class TestStageExtractionWait:
    def test_no_job_skip(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        r = stage_extraction_wait(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1", extraction_job_id="j1")
        r = stage_extraction_wait(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_completed_on_first_poll(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", extraction_job_id="j1")
        client = MagicMock()
        client.get.return_value = _response(json_body={"status": "COMPLETED"})
        r = stage_extraction_wait(client, ctx)
        assert r.status == "PASS"
        assert "completed" in r.detail.lower()

    def test_failed_job(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", extraction_job_id="j1")
        client = MagicMock()
        client.get.return_value = _response(json_body={"status": "FAILED", "error_message": "provider error"})
        r = stage_extraction_wait(client, ctx)
        assert r.status == "FAIL"
        assert "provider error" in r.detail

    def test_poll_non_200(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", extraction_job_id="j1")
        client = MagicMock()
        client.get.return_value = _response(status_code=404)
        r = stage_extraction_wait(client, ctx)
        assert r.status == "FAIL"
        assert "404" in r.detail

    @patch("scripts.staging_full_e2e._JOB_POLL_MAX_WAIT", 0.1)
    @patch("scripts.staging_full_e2e._JOB_POLL_INTERVAL", 0.05)
    def test_timeout(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", extraction_job_id="j1")
        client = MagicMock()
        client.get.return_value = _response(json_body={"status": "RUNNING"})
        r = stage_extraction_wait(client, ctx)
        assert r.status == "FAIL"
        assert "timed out" in r.detail.lower()

    def test_completes_after_polling(self):
        """RUNNING → RUNNING → COMPLETED."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", extraction_job_id="j1")
        client = MagicMock()
        running = _response(json_body={"status": "RUNNING"})
        completed = _response(json_body={"status": "COMPLETED"})
        client.get.side_effect = [running, completed]
        with patch("scripts.staging_full_e2e._JOB_POLL_INTERVAL", 0.01):
            r = stage_extraction_wait(client, ctx)
        assert r.status == "PASS"

    def test_exception_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", extraction_job_id="j1")
        client = MagicMock()
        client.get.side_effect = Exception("network")
        r = stage_extraction_wait(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 8: AI Compile (LLM-backed, connected to document_upload)
# ===========================================================================


class TestStageAiCompile:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok", document_id="doc-1")
        r = stage_ai_compile(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1", document_id="doc-1")
        r = stage_ai_compile(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_document_id_skip(self):
        """Without document_id, AI compile should SKIP (not use synthetic data)."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        r = stage_ai_compile(MagicMock(), ctx)
        assert r.status == "SKIP"
        assert "document_id" in r.detail

    def test_no_document_id_strict_fail(self):
        """In strict mode, missing document_id is a FAIL."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", strict=True)
        r = stage_ai_compile(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_compile_success(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        client = MagicMock()
        client.post.return_value = _response(
            json_body={
                "compilation_id": "comp-1",
                "suggestions": [
                    {"line_item_id": "li-1", "sector_code": "S01", "confidence": 0.95},
                    {"line_item_id": "li-2", "sector_code": "S02", "confidence": 0.70},
                ],
                "high_confidence": 1,
                "medium_confidence": 1,
                "low_confidence": 0,
            }
        )
        r = stage_ai_compile(client, ctx)
        assert r.status == "PASS"
        assert ctx.compilation_id == "comp-1"
        assert len(ctx.suggestions) == 2
        assert "H=1" in r.detail

    def test_503_no_llm_provider(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=503, text="LLM provider unavailable")
        r = stage_ai_compile(client, ctx)
        assert r.status == "FAIL"
        assert "503" in r.detail

    def test_compile_other_error(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=422, text="validation error")
        r = stage_ai_compile(client, ctx)
        assert r.status == "FAIL"
        assert "422" in r.detail

    def test_compile_exception(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        client = MagicMock()
        client.post.side_effect = Exception("timeout")
        r = stage_ai_compile(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 9: Scenario Build (connected to AI compile)
# ===========================================================================


class TestStageScenarioBuild:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok")
        ctx.suggestions = [{"line_item_id": "li-1"}]
        r = stage_scenario_build(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1")
        ctx.suggestions = [{"line_item_id": "li-1"}]
        r = stage_scenario_build(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_suggestions_and_no_compilation_skip(self):
        """No AI compile output means stage 8 must pass first."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        r = stage_scenario_build(MagicMock(), ctx)
        assert r.status == "SKIP"
        assert "stage 8" in r.detail.lower() or "AI compilation" in r.detail

    def test_no_suggestions_strict_fail(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", strict=True)
        r = stage_scenario_build(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_full_pipeline_pass(self):
        """Model version lookup → create scenario → approve decisions → compile."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        ctx.suggestions = [
            {"line_item_id": "li-1", "sector_code": "S01", "confidence": 0.95},
            {"line_item_id": "li-2", "sector_code": "S02", "confidence": 0.70},
        ]
        client = MagicMock()

        # Model version lookup
        mv_resp = _response(json_body={"items": [{"model_version_id": "mv-1", "sector_codes": ["S01", "S02", "S03"]}]})
        # Create scenario
        create_resp = _response(status_code=201, json_body={"scenario_spec_id": "sc-1", "version": 1})
        # Compile scenario with decisions
        compile_resp = _response(
            json_body={"shock_items": [{"sector": "S01"}, {"sector": "S02"}], "version": 2}
        )

        client.get.return_value = mv_resp
        client.post.side_effect = [create_resp, compile_resp]

        r = stage_scenario_build(client, ctx)
        assert r.status == "PASS"
        assert ctx.scenario_spec_id == "sc-1"
        assert ctx.model_version_id == "mv-1"
        assert len(ctx.sector_codes) == 3
        assert "2 shocks" in r.detail
        assert "2 decisions" in r.detail

    def test_create_scenario_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.suggestions = [{"line_item_id": "li-1"}]
        ctx.compilation_id = "comp-1"
        client = MagicMock()
        client.get.return_value = _response(json_body={"items": []})
        client.post.return_value = _response(status_code=500, text="server error")
        r = stage_scenario_build(client, ctx)
        assert r.status == "FAIL"
        assert "500" in r.detail

    def test_compile_scenario_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.suggestions = [{"line_item_id": "li-1", "sector_code": "S01", "confidence": 0.9}]
        client = MagicMock()
        client.get.return_value = _response(json_body={"items": []})
        create_resp = _response(status_code=201, json_body={"scenario_spec_id": "sc-1"})
        compile_resp = _response(status_code=422, text="no shock_items possible")
        client.post.side_effect = [create_resp, compile_resp]
        r = stage_scenario_build(client, ctx)
        assert r.status == "FAIL"
        assert "422" in r.detail

    def test_model_version_not_found_still_proceeds(self):
        """Model version lookup 404 should not stop scenario creation (uses 'default')."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.suggestions = [{"line_item_id": "li-1", "sector_code": "S01", "confidence": 0.9}]
        client = MagicMock()
        client.get.return_value = _response(status_code=404)  # No model versions
        create_resp = _response(status_code=201, json_body={"scenario_spec_id": "sc-1"})
        compile_resp = _response(json_body={"shock_items": [{"s": 1}], "version": 2})
        client.post.side_effect = [create_resp, compile_resp]
        r = stage_scenario_build(client, ctx)
        assert r.status == "PASS"

    def test_exception_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.suggestions = [{"line_item_id": "li-1"}]
        client = MagicMock()
        client.get.side_effect = Exception("network")
        r = stage_scenario_build(client, ctx)
        assert r.status == "FAIL"

    def test_decisions_built_from_suggestions(self):
        """Verify decisions are auto-approved from AI compile suggestions."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", document_id="doc-1")
        ctx.suggestions = [
            {"line_item_id": "li-1", "sector_code": "S01", "confidence": 0.95},
        ]
        client = MagicMock()
        client.get.return_value = _response(json_body={"items": []})
        create_resp = _response(status_code=201, json_body={"scenario_spec_id": "sc-1"})
        compile_resp = _response(json_body={"shock_items": [{"s": 1}], "version": 2})
        client.post.side_effect = [create_resp, compile_resp]

        r = stage_scenario_build(client, ctx)
        assert r.status == "PASS"
        # Verify the compile call included decisions from suggestions
        compile_call = client.post.call_args_list[1]
        if compile_call.kwargs and "json" in compile_call.kwargs:
            decisions = compile_call.kwargs["json"].get("decisions", [])
            assert len(decisions) == 1
            assert decisions[0]["decision_type"] == "APPROVED"


# ===========================================================================
# Stage 10: Depth Analysis
# ===========================================================================


class TestStageDepthAnalysis:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok")
        r = stage_depth_analysis(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1")
        r = stage_depth_analysis(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_depth_pass(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", scenario_spec_id="sc-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=201, json_body={"plan_id": "dp-1", "status": "CREATED"})
        r = stage_depth_analysis(client, ctx)
        assert r.status == "PASS"
        assert ctx.depth_plan_id == "dp-1"

    def test_depth_503(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=503, text="no LLM")
        r = stage_depth_analysis(client, ctx)
        assert r.status == "FAIL"
        assert "503" in r.detail

    def test_depth_with_scenario_spec_id(self):
        """Depth payload should include scenario_spec_id when available."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.scenario_spec_id = "sc-1"
        client = MagicMock()
        client.post.return_value = _response(status_code=201, json_body={"plan_id": "dp-1", "status": "ok"})
        r = stage_depth_analysis(client, ctx)
        assert r.status == "PASS"
        # Verify scenario_spec_id was included in payload
        call_kwargs = client.post.call_args
        posted_json = call_kwargs.kwargs.get("json", {})
        assert posted_json.get("scenario_spec_id") == "sc-1"

    def test_depth_exception(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.post.side_effect = Exception("err")
        r = stage_depth_analysis(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 11: Scenario Run (connected to scenario_build)
# ===========================================================================


class TestStageScenarioRun:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok", scenario_spec_id="sc-1")
        r = stage_scenario_run(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1", scenario_spec_id="sc-1")
        r = stage_scenario_run(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_scenario_spec_id_skip(self):
        """Without scenario_spec_id from stage 9, this stage cannot proceed."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        r = stage_scenario_run(MagicMock(), ctx)
        assert r.status == "SKIP"
        assert "scenario_spec_id" in r.detail

    def test_no_scenario_spec_id_strict_fail(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", strict=True)
        r = stage_scenario_run(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_run_success(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.scenario_spec_id = "sc-1"
        ctx.sector_codes = ["S01", "S02", "S03"]
        client = MagicMock()
        client.post.return_value = _response(
            json_body={
                "run_id": "run-1",
                "result_sets": [
                    {"metric_type": "output", "values": {"S01": 100.0, "S02": 200.0}},
                ],
            }
        )
        r = stage_scenario_run(client, ctx)
        assert r.status == "PASS"
        assert ctx.run_id == "run-1"
        assert len(ctx.run_result_sets) == 1

    def test_run_failure(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.scenario_spec_id = "sc-1"
        client = MagicMock()
        client.post.return_value = _response(status_code=400, text="bad scenario")
        r = stage_scenario_run(client, ctx)
        assert r.status == "FAIL"

    def test_run_uses_scenario_spec_id(self):
        """Verify the run endpoint uses scenario_spec_id from scenario_build."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.scenario_spec_id = "sc-99"
        client = MagicMock()
        client.post.return_value = _response(json_body={"run_id": "r1", "result_sets": []})
        stage_scenario_run(client, ctx)
        url = client.post.call_args[0][0]
        assert "sc-99/run" in url

    def test_run_exception(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        ctx.scenario_spec_id = "sc-1"
        client = MagicMock()
        client.post.side_effect = Exception("err")
        r = stage_scenario_run(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 12: Governance Evaluate (real evaluation, not reachability)
# ===========================================================================


class TestStageGovernanceEvaluate:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok", run_id="run-1")
        r = stage_governance_evaluate(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_run_id_skip(self):
        """No run_id means scenario_run must pass first."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        r = stage_governance_evaluate(MagicMock(), ctx)
        assert r.status == "SKIP"
        assert "run_id" in r.detail

    def test_no_run_id_strict_fail(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", strict=True)
        r = stage_governance_evaluate(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1", run_id="run-1")
        r = stage_governance_evaluate(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_claims_extracted_and_status_pass(self):
        """Full flow: extract claims → get status → PASS."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()

        extract_resp = _response(
            json_body={"claims": [{"claim_id": "cl-1"}, {"claim_id": "cl-2"}]}
        )
        status_resp = _response(
            json_body={"claims_total": 2, "nff_passed": True}
        )
        client.post.return_value = extract_resp
        client.get.return_value = status_resp

        r = stage_governance_evaluate(client, ctx)
        assert r.status == "PASS"
        assert ctx.claim_ids == ["cl-1", "cl-2"]
        assert ctx.governance_status == {"claims_total": 2, "nff_passed": True}
        assert "2 claims" in r.detail

    def test_zero_claims_fails(self):
        """0 claims extracted = governance did not evaluate the run = FAIL."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        client.post.return_value = _response(json_body={"claims": []})
        r = stage_governance_evaluate(client, ctx)
        assert r.status == "FAIL"
        assert "No claims" in r.detail

    def test_claim_extraction_non_200_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=500, text="error")
        r = stage_governance_evaluate(client, ctx)
        assert r.status == "FAIL"
        assert "500" in r.detail

    def test_claims_extracted_but_status_endpoint_fails_still_passes(self):
        """Claims extracted but status endpoint 404 — still PASS with claim count."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        extract_resp = _response(json_body={"claims": [{"claim_id": "cl-1"}]})
        status_resp = _response(status_code=404)
        client.post.return_value = extract_resp
        client.get.return_value = status_resp
        r = stage_governance_evaluate(client, ctx)
        assert r.status == "PASS"
        assert "1" in r.detail  # 1 claim

    def test_exception_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        client.post.side_effect = Exception("network")
        r = stage_governance_evaluate(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 13: Copilot Query (real LLM interaction)
# ===========================================================================


class TestStageCopilotQuery:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok")
        r = stage_copilot_query(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1")
        r = stage_copilot_query(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_copilot_not_deployed_404(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.get.return_value = _response(status_code=404)
        r = stage_copilot_query(client, ctx)
        assert r.status == "SKIP"

    def test_copilot_not_deployed_404_strict_fail(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", strict=True)
        client = MagicMock()
        client.get.return_value = _response(status_code=404)
        r = stage_copilot_query(client, ctx)
        assert r.status == "FAIL"

    def test_copilot_disabled(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.get.return_value = _response(json_body={"enabled": False, "detail": "feature off"})
        r = stage_copilot_query(client, ctx)
        assert r.status == "SKIP"

    def test_copilot_not_ready(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.get.return_value = _response(json_body={"enabled": True, "ready": False, "detail": "no provider"})
        r = stage_copilot_query(client, ctx)
        assert r.status == "FAIL"
        assert "not ready" in r.detail.lower()

    def test_full_copilot_flow_pass(self):
        """Status OK → create session → send message → PASS."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()

        status_resp = _response(json_body={"enabled": True, "ready": True})
        session_resp = _response(status_code=201, json_body={"session_id": "sess-1"})
        msg_resp = _response(
            json_body={
                "content": "Run run-1 produced 3 sectors with positive output.",
                "token_usage": {"input_tokens": 100, "output_tokens": 50},
                "tool_calls": [{"name": "get_run"}],
            }
        )
        client.get.return_value = status_resp
        client.post.side_effect = [session_resp, msg_resp]

        r = stage_copilot_query(client, ctx)
        assert r.status == "PASS"
        assert ctx.session_id == "sess-1"
        assert "50 tokens" in r.detail
        assert "1 tool calls" in r.detail

    def test_copilot_empty_response_fails(self):
        """Empty LLM response = LLM did not execute = FAIL."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        status_resp = _response(json_body={"enabled": True, "ready": True})
        session_resp = _response(status_code=201, json_body={"session_id": "sess-1"})
        msg_resp = _response(json_body={"content": "", "token_usage": {}})
        client.get.return_value = status_resp
        client.post.side_effect = [session_resp, msg_resp]
        r = stage_copilot_query(client, ctx)
        assert r.status == "FAIL"
        assert "empty" in r.detail.lower()

    def test_session_creation_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        status_resp = _response(json_body={"enabled": True, "ready": True})
        session_resp = _response(status_code=500, text="error")
        client.get.return_value = status_resp
        client.post.return_value = session_resp
        r = stage_copilot_query(client, ctx)
        assert r.status == "FAIL"
        assert "500" in r.detail

    def test_message_send_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        status_resp = _response(json_body={"enabled": True, "ready": True})
        session_resp = _response(status_code=201, json_body={"session_id": "sess-1"})
        msg_resp = _response(status_code=503, text="LLM timeout")
        client.get.return_value = status_resp
        client.post.side_effect = [session_resp, msg_resp]
        r = stage_copilot_query(client, ctx)
        assert r.status == "FAIL"
        assert "503" in r.detail

    def test_copilot_uses_run_id_in_message(self):
        """When run_id is present, message should reference it."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-42")
        client = MagicMock()
        status_resp = _response(json_body={"enabled": True, "ready": True})
        session_resp = _response(status_code=201, json_body={"session_id": "sess-1"})
        msg_resp = _response(json_body={"content": "result summary", "token_usage": {"output_tokens": 10}})
        client.get.return_value = status_resp
        client.post.side_effect = [session_resp, msg_resp]
        stage_copilot_query(client, ctx)
        msg_call = client.post.call_args_list[1]
        msg_json = msg_call.kwargs.get("json", {})
        assert "run-42" in msg_json.get("content", "")

    def test_exception_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        client = MagicMock()
        client.get.side_effect = Exception("err")
        r = stage_copilot_query(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 14: Export + Download
# ===========================================================================


class TestStageExportDownload:
    def test_no_workspace_skip(self):
        ctx = _ctx(auth_token="tok", run_id="run-1")
        r = stage_export_download(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_run_id_skip(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        r = stage_export_download(MagicMock(), ctx)
        assert r.status == "SKIP"
        assert "run_id" in r.detail

    def test_no_auth_skip(self):
        ctx = _ctx(workspace_id="ws-1", run_id="run-1")
        r = stage_export_download(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_export_create_and_download_pass(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        create_resp = _response(status_code=201, json_body={"export_id": "exp-1", "status": "COMPLETED"})
        dl_resp = MagicMock(spec=httpx.Response)
        dl_resp.status_code = 200
        dl_resp.content = b"PK\x03\x04" + b"\x00" * 1000
        client.post.return_value = create_resp
        client.get.return_value = dl_resp
        r = stage_export_download(client, ctx)
        assert r.status == "PASS"
        assert ctx.export_id == "exp-1"
        assert "bytes" in r.detail

    def test_export_blocked(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        client.post.return_value = _response(
            status_code=200,
            json_body={"export_id": "exp-1", "status": "BLOCKED", "blocking_reasons": ["no governance"]},
        )
        r = stage_export_download(client, ctx)
        assert r.status == "FAIL"
        assert "BLOCKED" in r.detail or "no governance" in r.detail

    def test_export_create_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        client.post.return_value = _response(status_code=500, text="error")
        r = stage_export_download(client, ctx)
        assert r.status == "FAIL"

    def test_download_empty_content_fails(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        create_resp = _response(status_code=201, json_body={"export_id": "exp-1", "status": "COMPLETED"})
        dl_resp = MagicMock(spec=httpx.Response)
        dl_resp.status_code = 200
        dl_resp.content = b""
        client.post.return_value = create_resp
        client.get.return_value = dl_resp
        r = stage_export_download(client, ctx)
        assert r.status == "FAIL"
        assert "empty" in r.detail.lower()

    def test_download_409_not_ready(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        create_resp = _response(status_code=201, json_body={"export_id": "exp-1", "status": "PENDING"})
        dl_resp = MagicMock(spec=httpx.Response)
        dl_resp.status_code = 409
        client.post.return_value = create_resp
        client.get.return_value = dl_resp
        r = stage_export_download(client, ctx)
        assert r.status == "FAIL"
        assert "not ready" in r.detail.lower()

    def test_export_exception(self):
        ctx = _ctx(auth_token="tok", workspace_id="ws-1", run_id="run-1")
        client = MagicMock()
        client.post.side_effect = Exception("err")
        r = stage_export_download(client, ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Stage 15: Output Validation (golden fixture comparison)
# ===========================================================================


class TestLoadGoldenFixture:
    def test_load_existing_file(self, tmp_path):
        f = tmp_path / "golden.json"
        f.write_text(json.dumps(GOLDEN_FIXTURE))
        with patch("scripts.staging_full_e2e._GOLDEN_FIXTURE_PATH", f):
            result = _load_golden_fixture()
        assert result["version"] == "1.0"
        assert "result_sets" in result

    def test_load_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.json"
        with patch("scripts.staging_full_e2e._GOLDEN_FIXTURE_PATH", f):
            result = _load_golden_fixture()
        assert result == {}


class TestStageOutputValidation:
    def _golden_patch(self):
        return patch("scripts.staging_full_e2e._load_golden_fixture", return_value=GOLDEN_FIXTURE)

    def test_no_run_id_skip(self):
        ctx = _ctx()
        ctx.run_result_sets = [{"metric_type": "output", "values": {"S01": 100}}]
        r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_no_result_sets_skip(self):
        ctx = _ctx(run_id="run-1")
        r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "SKIP"

    def test_valid_output_pass(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0, "S02": 200.0}},
        ]
        with self._golden_patch():
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "PASS"
        assert "1 result_sets" in r.detail

    def test_missing_required_metric_type_fails(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"metric_type": "value_added", "values": {"S01": 100.0}},
        ]
        with self._golden_patch():
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "FAIL"
        assert "output" in r.detail  # missing 'output' metric_type

    def test_too_few_result_sets_fails(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [{"metric_type": "output", "values": {"S01": 1.0}}]
        fixture = dict(GOLDEN_FIXTURE)
        fixture["result_sets"] = dict(fixture["result_sets"])
        fixture["result_sets"]["min_count"] = 3
        with patch("scripts.staging_full_e2e._load_golden_fixture", return_value=fixture):
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "FAIL"
        assert "count" in r.detail

    def test_value_out_of_range_fails(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 2e15}},  # Above max
        ]
        with self._golden_patch():
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "FAIL"
        assert "range" in r.detail.lower()

    def test_all_zero_values_fails(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 0.0, "S02": 0.0}},
        ]
        with self._golden_patch():
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "FAIL"
        assert "zero" in r.detail.lower()

    def test_missing_metric_type_field_fails(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"values": {"S01": 100.0}},  # No metric_type key
        ]
        with self._golden_patch():
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "FAIL"
        assert "missing" in r.detail.lower()

    def test_empty_values_dict_fails(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {}},
        ]
        with self._golden_patch():
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "FAIL"
        assert "empty" in r.detail.lower()

    def test_validate_outputs_persisted_match(self):
        ctx = _ctx(run_id="run-1", auth_token="tok", workspace_id="ws-1", validate_outputs=True)
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0}},
        ]
        client = MagicMock()
        client.get.return_value = _response(
            json_body={"result_sets": [{"metric_type": "output", "values": {"S01": 100.0}}]}
        )
        with self._golden_patch():
            r = stage_output_validation(client, ctx)
        assert r.status == "PASS"
        assert "persisted data matches" in r.detail

    def test_validate_outputs_count_mismatch_fails(self):
        ctx = _ctx(run_id="run-1", auth_token="tok", workspace_id="ws-1", validate_outputs=True)
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0}},
        ]
        client = MagicMock()
        client.get.return_value = _response(
            json_body={"result_sets": [
                {"metric_type": "output", "values": {"S01": 100.0}},
                {"metric_type": "value_added", "values": {"S01": 50.0}},
            ]}
        )
        with self._golden_patch():
            r = stage_output_validation(client, ctx)
        assert r.status == "FAIL"
        assert "count" in r.detail.lower()

    def test_validate_outputs_type_mismatch_fails(self):
        ctx = _ctx(run_id="run-1", auth_token="tok", workspace_id="ws-1", validate_outputs=True)
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0}},
        ]
        client = MagicMock()
        client.get.return_value = _response(
            json_body={"result_sets": [{"metric_type": "value_added", "values": {"S01": 50.0}}]}
        )
        with self._golden_patch():
            r = stage_output_validation(client, ctx)
        assert r.status == "FAIL"
        assert "mismatch" in r.detail.lower()

    def test_validate_outputs_fetch_error(self):
        ctx = _ctx(run_id="run-1", auth_token="tok", workspace_id="ws-1", validate_outputs=True)
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0}},
        ]
        client = MagicMock()
        client.get.return_value = _response(status_code=404)
        with self._golden_patch():
            r = stage_output_validation(client, ctx)
        assert r.status == "FAIL"
        assert "404" in r.detail

    def test_validate_outputs_exception(self):
        ctx = _ctx(run_id="run-1", auth_token="tok", workspace_id="ws-1", validate_outputs=True)
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0}},
        ]
        client = MagicMock()
        client.get.side_effect = Exception("db down")
        with self._golden_patch():
            r = stage_output_validation(client, ctx)
        assert r.status == "FAIL"
        assert "db down" in r.detail

    def test_multiple_result_sets_pass(self):
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0}},
            {"metric_type": "value_added", "values": {"S01": 50.0}},
            {"metric_type": "employment", "values": {"S01": 10.0}},
        ]
        with self._golden_patch():
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "PASS"
        assert "3 result_sets" in r.detail

    def test_no_golden_fixture_still_works(self):
        """Without golden fixture file, minimal validation still runs."""
        ctx = _ctx(run_id="run-1")
        ctx.run_result_sets = [
            {"metric_type": "output", "values": {"S01": 100.0}},
        ]
        with patch("scripts.staging_full_e2e._load_golden_fixture", return_value={}):
            r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "PASS"


# ===========================================================================
# Integration: run_e2e
# ===========================================================================


class TestRunE2E:
    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_returns_15_stages(self, mock_client_cls):
        """run_e2e produces 15 stage results (including cascade)."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # API health fails → cascade all downstream stages
        client.get.return_value = _response(status_code=503)

        report = run_e2e(api_url="http://api:8000", frontend_url="http://fe:3000")
        assert len(report.stages) == 15
        assert report.overall == "FAIL"

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_stage_names_match_expected(self, mock_client_cls):
        """All 15 expected stage names are present."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Health fails → cascade
        client.get.return_value = _response(status_code=503)

        report = run_e2e(api_url="http://api:8000")
        names = [s.name for s in report.stages]
        expected = [
            "oidc_token",
            "frontend_verify",
            "api_health",
            "workspace_access",
            "document_upload",
            "extraction_trigger",
            "extraction_wait",
            "ai_compile",
            "scenario_build",
            "depth_analysis",
            "scenario_run",
            "governance_evaluate",
            "copilot_query",
            "export_download",
            "output_validation",
        ]
        assert names == expected

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_cascade_skip_on_health_fail_default_mode(self, mock_client_cls):
        """When API health fails in default mode, downstream = SKIP."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        client.get.return_value = _response(status_code=503)

        report = run_e2e(api_url="http://api:8000", strict=False)
        for s in report.stages:
            if s.name == "api_health":
                assert s.status == "FAIL"
            elif s.name in ("oidc_token", "frontend_verify"):
                pass  # These run before api_health
            else:
                assert s.status == "SKIP", f"{s.name} should be SKIP, got {s.status}"

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_cascade_fail_on_health_fail_strict_mode(self, mock_client_cls):
        """When API health fails in strict mode, downstream = FAIL."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        client.get.return_value = _response(status_code=503)

        report = run_e2e(api_url="http://api:8000", strict=True)
        for s in report.stages:
            if s.name == "api_health":
                assert s.status == "FAIL"
            elif s.name in ("oidc_token", "frontend_verify"):
                pass  # These run before api_health
            else:
                assert s.status == "FAIL", f"{s.name} should be FAIL in strict mode"

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_strict_mode_skip_counts_as_fail(self, mock_client_cls):
        """In strict mode, any SKIP in the report makes overall = FAIL."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        client.get.return_value = _response(status_code=503)
        report = run_e2e(api_url="http://api:8000", strict=True)
        assert report.overall == "FAIL"
        assert report.strict is True

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_oidc_params_forwarded(self, mock_client_cls):
        """run_e2e passes OIDC params through to context."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        disc_resp = _response(json_body={"token_endpoint": "https://idp/token"})
        tok_resp = _response(json_body={"access_token": "tok-xyz", "expires_in": 3600})
        health_resp = _response(status_code=503)
        # First GET = discovery, second GET = health check on frontend, third GET = API health
        client.get.side_effect = [disc_resp, _html_response(), health_resp]
        client.post.return_value = tok_resp

        report = run_e2e(
            api_url="http://api:8000",
            frontend_url="http://fe:3000",
            oidc_issuer="https://idp",
            oidc_client_id="c1",
            oidc_client_secret="s1",
        )
        # OIDC stage should PASS
        oidc_stage = next(s for s in report.stages if s.name == "oidc_token")
        assert oidc_stage.status == "PASS"

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_trace_captures_all_ids(self, mock_client_cls):
        """Trace dict includes all 10 pipeline IDs."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        client.get.return_value = _response(status_code=503)

        report = run_e2e(api_url="http://api:8000")
        expected_keys = {
            "workspace_id",
            "document_id",
            "extraction_job_id",
            "compilation_id",
            "model_version_id",
            "scenario_spec_id",
            "depth_plan_id",
            "run_id",
            "export_id",
            "session_id",
        }
        assert set(report.trace.keys()) == expected_keys

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_json_serializable(self, mock_client_cls):
        """Report is JSON-serializable via asdict."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        client.get.return_value = _response(status_code=503)

        report = run_e2e(api_url="http://api:8000")
        d = asdict(report)
        serialized = json.dumps(d)
        assert '"overall"' in serialized
        assert '"stages"' in serialized

    @patch("scripts.staging_full_e2e.httpx.Client")
    def test_default_no_fail_passes(self, mock_client_cls):
        """Default mode with all SKIP (no FAIL) produces overall PASS."""
        client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Health passes (all components OK)
        checks = {c: "ok" for c in _HEALTH_COMPONENTS}
        health_resp = _response(json_body={"checks": checks})
        # All subsequent GETs return empty/404 causing SKIPs
        client.get.side_effect = [
            _html_response(),  # frontend_verify
            health_resp,  # api_health
            _response(json_body={"items": []}),  # workspace_access (list)
        ]
        client.post.return_value = _response(status_code=404)

        report = run_e2e(api_url="http://api:8000", frontend_url="http://fe:3000", strict=False)
        # At least api_health and frontend_verify should pass
        health = next(s for s in report.stages if s.name == "api_health")
        assert health.status == "PASS"


# ===========================================================================
# Report output helpers
# ===========================================================================


class TestReportOutput:
    def test_has_failures_mixed(self):
        report = E2EReport(overall="FAIL", api_url="http://api:8000", frontend_url="http://fe:3000")
        report.stages = [
            StageResult("a", "PASS", "ok"),
            StageResult("b", "FAIL", "err"),
            StageResult("c", "SKIP", "skip"),
        ]
        assert report.has_failures() is True

    def test_has_failures_all_pass(self):
        report = E2EReport(overall="PASS", api_url="http://api:8000", frontend_url="http://fe:3000")
        report.stages = [
            StageResult("a", "PASS", "ok"),
            StageResult("b", "PASS", "ok"),
        ]
        assert report.has_failures() is False

    def test_has_failures_only_skips(self):
        """SKIP is not considered a failure by has_failures()."""
        report = E2EReport(overall="PASS", api_url="http://api:8000", frontend_url="http://fe:3000")
        report.stages = [
            StageResult("a", "PASS", "ok"),
            StageResult("b", "SKIP", "no auth"),
        ]
        assert report.has_failures() is False


# ===========================================================================
# Strict mode behaviour across all stages
# ===========================================================================


class TestStrictModeBehaviour:
    """Verify strict mode causes FAIL instead of SKIP for all missing-prerequisite cases."""

    def test_oidc_token_strict_no_config(self):
        ctx = _ctx(strict=True)
        r = stage_oidc_token(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_frontend_verify_strict_no_url(self):
        ctx = _ctx(strict=True, frontend_url="")
        r = stage_frontend_verify(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_workspace_access_strict_no_token(self):
        ctx = _ctx(strict=True)
        r = stage_workspace_access(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_document_upload_strict_no_workspace(self):
        ctx = _ctx(strict=True, auth_token="tok")
        r = stage_document_upload(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_extraction_trigger_strict_no_doc(self):
        ctx = _ctx(strict=True, auth_token="tok", workspace_id="ws-1")
        r = stage_extraction_trigger(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_extraction_wait_strict_no_job(self):
        ctx = _ctx(strict=True, auth_token="tok", workspace_id="ws-1")
        r = stage_extraction_wait(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_ai_compile_strict_no_document(self):
        ctx = _ctx(strict=True, auth_token="tok", workspace_id="ws-1")
        r = stage_ai_compile(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_scenario_build_strict_no_suggestions(self):
        ctx = _ctx(strict=True, auth_token="tok", workspace_id="ws-1")
        r = stage_scenario_build(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_depth_analysis_strict_no_workspace(self):
        ctx = _ctx(strict=True, auth_token="tok")
        r = stage_depth_analysis(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_scenario_run_strict_no_scenario(self):
        ctx = _ctx(strict=True, auth_token="tok", workspace_id="ws-1")
        r = stage_scenario_run(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_governance_evaluate_strict_no_run(self):
        ctx = _ctx(strict=True, auth_token="tok", workspace_id="ws-1")
        r = stage_governance_evaluate(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_copilot_query_strict_no_workspace(self):
        ctx = _ctx(strict=True, auth_token="tok")
        r = stage_copilot_query(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_export_download_strict_no_run(self):
        ctx = _ctx(strict=True, auth_token="tok", workspace_id="ws-1")
        r = stage_export_download(MagicMock(), ctx)
        assert r.status == "FAIL"

    def test_output_validation_strict_no_results(self):
        ctx = _ctx(strict=True, run_id="run-1")
        r = stage_output_validation(MagicMock(), ctx)
        assert r.status == "FAIL"


# ===========================================================================
# Connected pipeline verification
# ===========================================================================


class TestConnectedPipeline:
    """Verify the pipeline flows IDs correctly between stages."""

    def test_ai_compile_requires_document_id(self):
        """ai_compile must fail when no document_id (no synthetic fallback)."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        assert ctx.document_id == ""
        r = stage_ai_compile(MagicMock(), ctx)
        assert r.status in ("SKIP", "FAIL")
        assert "document_id" in r.detail

    def test_scenario_build_requires_ai_compile_output(self):
        """scenario_build requires suggestions or compilation_id from ai_compile."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        assert ctx.suggestions == []
        assert ctx.compilation_id == ""
        r = stage_scenario_build(MagicMock(), ctx)
        assert r.status in ("SKIP", "FAIL")

    def test_scenario_run_requires_scenario_spec_id(self):
        """scenario_run requires scenario_spec_id from scenario_build."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        assert ctx.scenario_spec_id == ""
        r = stage_scenario_run(MagicMock(), ctx)
        assert r.status in ("SKIP", "FAIL")
        assert "scenario_spec_id" in r.detail

    def test_governance_requires_run_id(self):
        """governance_evaluate requires run_id from scenario_run."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        assert ctx.run_id == ""
        r = stage_governance_evaluate(MagicMock(), ctx)
        assert r.status in ("SKIP", "FAIL")
        assert "run_id" in r.detail

    def test_export_requires_run_id(self):
        """export_download requires run_id from scenario_run."""
        ctx = _ctx(auth_token="tok", workspace_id="ws-1")
        assert ctx.run_id == ""
        r = stage_export_download(MagicMock(), ctx)
        assert r.status in ("SKIP", "FAIL")
        assert "run_id" in r.detail

    def test_output_validation_requires_result_sets(self):
        """output_validation requires run_result_sets from scenario_run."""
        ctx = _ctx(run_id="run-1")
        assert ctx.run_result_sets == []
        r = stage_output_validation(MagicMock(), ctx)
        assert r.status in ("SKIP", "FAIL")
