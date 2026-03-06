"""Tests for staging smoke harness.

Tests verify:
- StageResult/SmokeReport dataclasses work correctly
- has_failures() correctly identifies FAIL status
- Each stage function returns the correct status for mocked HTTP responses
- run_smoke cascades SKIP when startup fails
- Copilot smoke uses server-side detection (no local env gating)
- Unexpected statuses are FAIL, never WARN
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from scripts.staging_smoke import (
    SmokeReport,
    StageResult,
    run_smoke,
    stage_api_schema,
    stage_auth_enforcement,
    stage_copilot_smoke,
    stage_health_components,
    stage_readiness,
    stage_startup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    """Build a mock httpx.Response with the given status and JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("No JSON body")
    return resp


def _mock_client(**route_responses: MagicMock) -> MagicMock:
    """Build a mock httpx.Client that returns per-URL responses.

    ``route_responses`` maps URL substrings to mock responses.
    """
    client = MagicMock(spec=httpx.Client)

    def _get(url: str, **kwargs):
        for key, resp in route_responses.items():
            if key in url:
                return resp
        raise httpx.ConnectError(f"No mock for {url}")

    def _post(url: str, **kwargs):
        for key, resp in route_responses.items():
            if key in url:
                return resp
        raise httpx.ConnectError(f"No mock for {url}")

    client.get = MagicMock(side_effect=_get)
    client.post = MagicMock(side_effect=_post)
    return client


# ---------------------------------------------------------------------------
# Test: StageResult / SmokeReport dataclasses
# ---------------------------------------------------------------------------


class TestStageResult:
    """StageResult dataclass has the expected fields."""

    def test_stage_result_fields(self) -> None:
        sr = StageResult(name="test", status="PASS", detail="ok")
        assert sr.name == "test"
        assert sr.status == "PASS"
        assert sr.detail == "ok"


class TestSmokeReport:
    """SmokeReport correctly reports failures."""

    def test_no_failures(self) -> None:
        report = SmokeReport(
            overall="PASS",
            stages=[
                StageResult(name="a", status="PASS", detail="ok"),
                StageResult(name="b", status="SKIP", detail="skipped"),
            ],
        )
        assert report.has_failures() is False

    def test_with_failure(self) -> None:
        report = SmokeReport(
            overall="FAIL",
            stages=[
                StageResult(name="a", status="PASS", detail="ok"),
                StageResult(name="b", status="FAIL", detail="broken"),
            ],
        )
        assert report.has_failures() is True


# ---------------------------------------------------------------------------
# Test: stage_startup
# ---------------------------------------------------------------------------


class TestStageStartup:
    """stage_startup verifies server reachability."""

    def test_startup_pass(self) -> None:
        client = _mock_client(
            version=_mock_response(200, {"version": "1.0.0"}),
        )
        result = stage_startup(client, "http://localhost:8000")
        assert result.status == "PASS"
        assert "1.0.0" in result.detail

    def test_startup_non_200(self) -> None:
        client = _mock_client(
            version=_mock_response(503, None),
        )
        result = stage_startup(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "503" in result.detail

    def test_startup_connect_error(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get = MagicMock(side_effect=httpx.ConnectError("refused"))
        result = stage_startup(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "Cannot connect" in result.detail


# ---------------------------------------------------------------------------
# Test: stage_readiness
# ---------------------------------------------------------------------------


class TestStageReadiness:
    """stage_readiness checks /readiness returns ready=true."""

    def test_readiness_pass(self) -> None:
        client = _mock_client(
            readiness=_mock_response(200, {"ready": True}),
        )
        result = stage_readiness(client, "http://localhost:8000")
        assert result.status == "PASS"

    def test_readiness_not_ready(self) -> None:
        client = _mock_client(
            readiness=_mock_response(200, {"ready": False}),
        )
        result = stage_readiness(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "not ready" in result.detail.lower()

    def test_readiness_non_200(self) -> None:
        client = _mock_client(
            readiness=_mock_response(500, None),
        )
        result = stage_readiness(client, "http://localhost:8000")
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: stage_auth_enforcement
# ---------------------------------------------------------------------------


class TestStageAuthEnforcement:
    """stage_auth_enforcement checks unauthenticated request returns 401."""

    def test_auth_returns_401(self) -> None:
        client = _mock_client(
            workspaces=_mock_response(401, None),
        )
        result = stage_auth_enforcement(client, "http://localhost:8000")
        assert result.status == "PASS"

    def test_auth_returns_200(self) -> None:
        """200 without auth is a failure (auth bypass)."""
        client = _mock_client(
            workspaces=_mock_response(200, None),
        )
        result = stage_auth_enforcement(client, "http://localhost:8000")
        assert result.status == "FAIL"


# ---------------------------------------------------------------------------
# Test: stage_health_components
# ---------------------------------------------------------------------------


class TestStageHealthComponents:
    """stage_health_components checks all 4 components present."""

    def test_all_components_present(self) -> None:
        client = _mock_client(
            health=_mock_response(200, {
                "checks": {
                    "api": "ok",
                    "database": "ok",
                    "redis": "ok",
                    "object_storage": "ok",
                },
            }),
        )
        result = stage_health_components(client, "http://localhost:8000")
        assert result.status == "PASS"

    def test_missing_component(self) -> None:
        client = _mock_client(
            health=_mock_response(200, {
                "checks": {
                    "api": "ok",
                    "database": "ok",
                },
            }),
        )
        result = stage_health_components(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "Missing" in result.detail


# ---------------------------------------------------------------------------
# Test: stage_api_schema
# ---------------------------------------------------------------------------


class TestStageApiSchema:
    """stage_api_schema checks /openapi.json is valid with paths."""

    def test_valid_schema(self) -> None:
        client = _mock_client(
            openapi=_mock_response(200, {
                "paths": {"/v1/workspaces": {}, "/health": {}},
            }),
        )
        result = stage_api_schema(client, "http://localhost:8000")
        assert result.status == "PASS"
        assert "2 paths" in result.detail

    def test_empty_paths(self) -> None:
        client = _mock_client(
            openapi=_mock_response(200, {"paths": {}}),
        )
        result = stage_api_schema(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "no paths" in result.detail.lower()


# ---------------------------------------------------------------------------
# Test: stage_copilot_smoke
# ---------------------------------------------------------------------------


class TestStageCopilotSmoke:
    """stage_copilot_smoke probes /api/copilot/status for runtime readiness."""

    def test_copilot_ready_passes(self) -> None:
        """enabled=true, ready=true → PASS with providers listed."""
        client = _mock_client(
            copilot=_mock_response(200, {
                "enabled": True,
                "ready": True,
                "providers": ["LOCAL", "ANTHROPIC"],
                "detail": "Copilot runtime ready",
            }),
        )
        result = stage_copilot_smoke(client, "http://localhost:8000")
        assert result.status == "PASS"
        assert "ANTHROPIC" in result.detail

    def test_copilot_disabled_skips(self) -> None:
        """enabled=false → SKIP (copilot intentionally off)."""
        client = _mock_client(
            copilot=_mock_response(200, {
                "enabled": False,
                "ready": False,
                "providers": [],
                "detail": "COPILOT_ENABLED=false",
            }),
        )
        result = stage_copilot_smoke(client, "http://localhost:8000")
        assert result.status == "SKIP"
        assert "disabled" in result.detail.lower()

    def test_copilot_enabled_not_ready_fails(self) -> None:
        """enabled=true, ready=false → FAIL (no LLM providers)."""
        client = _mock_client(
            copilot=_mock_response(200, {
                "enabled": True,
                "ready": False,
                "providers": [],
                "detail": "No LLM providers available",
            }),
        )
        result = stage_copilot_smoke(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "not ready" in result.detail.lower()

    def test_copilot_404_skips(self) -> None:
        """404 means endpoint not deployed — SKIP gracefully."""
        client = _mock_client(
            copilot=_mock_response(404, None),
        )
        result = stage_copilot_smoke(client, "http://localhost:8000")
        assert result.status == "SKIP"
        assert "404" in result.detail

    def test_copilot_500_fails(self) -> None:
        """Server error must FAIL."""
        client = _mock_client(
            copilot=_mock_response(500, None),
        )
        result = stage_copilot_smoke(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "500" in result.detail

    def test_copilot_unexpected_status_fails(self) -> None:
        """Any unexpected status (e.g. 301) must FAIL, not WARN."""
        client = _mock_client(
            copilot=_mock_response(301, None),
        )
        result = stage_copilot_smoke(client, "http://localhost:8000")
        assert result.status == "FAIL"
        assert "Unexpected" in result.detail

    def test_copilot_no_local_env_gating(self) -> None:
        """Copilot smoke must NOT read local env vars to decide execution.

        Even with no COPILOT_ENABLED or LLM keys in the local env,
        the stage must still probe the server.
        """
        client = _mock_client(
            copilot=_mock_response(200, {
                "enabled": True,
                "ready": True,
                "providers": ["LOCAL"],
                "detail": "Copilot runtime ready",
            }),
        )
        with patch.dict("os.environ", {}, clear=True):
            result = stage_copilot_smoke(client, "http://localhost:8000")
        assert result.status == "PASS"

    def test_copilot_probes_status_not_chat(self) -> None:
        """Verify the stage hits /api/copilot/status, not /chat/sessions."""
        client = MagicMock(spec=httpx.Client)
        client.get = MagicMock(return_value=_mock_response(200, {
            "enabled": True,
            "ready": True,
            "providers": ["LOCAL"],
            "detail": "ok",
        }))

        stage_copilot_smoke(client, "http://localhost:8000")

        call_args = client.get.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "/api/copilot/status" in url
        assert "/chat/" not in url


# ---------------------------------------------------------------------------
# Test: run_smoke cascade-skip
# ---------------------------------------------------------------------------


class TestRunSmokeCascade:
    """run_smoke cascades SKIP when startup fails."""

    def test_startup_fail_cascades_skip(self) -> None:
        """If startup fails, all remaining stages are SKIP and overall is FAIL."""
        # Build the mock client *before* patching httpx.Client
        mock_client = MagicMock()
        mock_client.get = MagicMock(
            side_effect=httpx.ConnectError("refused"),
        )

        ctx_manager = MagicMock()
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_smoke.httpx.Client", return_value=ctx_manager):
            report = run_smoke("http://localhost:9999")

        assert report.overall == "FAIL"
        assert report.stages[0].name == "startup"
        assert report.stages[0].status == "FAIL"
        # All remaining stages should be SKIP
        for stage in report.stages[1:]:
            assert stage.status == "SKIP", f"{stage.name} should be SKIP"
        assert len(report.stages) == 6  # all 6 stages present

    def test_all_pass_overall_pass(self) -> None:
        """If all stages pass, overall is PASS."""
        mock_client = _mock_client(
            version=_mock_response(200, {"version": "1.0.0"}),
            readiness=_mock_response(200, {"ready": True}),
            workspaces=_mock_response(401, None),
            health=_mock_response(200, {
                "checks": {
                    "api": "ok", "database": "ok",
                    "redis": "ok", "object_storage": "ok",
                },
            }),
            openapi=_mock_response(200, {"paths": {"/v1/a": {}}}),
            copilot=_mock_response(200, {
                "enabled": True, "ready": True,
                "providers": ["LOCAL"], "detail": "ok",
            }),
        )

        ctx_manager = MagicMock()
        ctx_manager.__enter__ = MagicMock(return_value=mock_client)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        with patch("scripts.staging_smoke.httpx.Client", return_value=ctx_manager):
            report = run_smoke("http://localhost:8000")

        assert report.overall == "PASS"
        assert report.has_failures() is False
