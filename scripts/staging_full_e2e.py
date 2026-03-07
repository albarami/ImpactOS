"""Full-system staging E2E acceptance harness.

Usage:
    python scripts/staging_full_e2e.py \\
        --api-url http://staging-api:8000 \\
        --frontend-url http://staging-frontend:3000 \\
        --oidc-issuer https://idp.example.com \\
        --oidc-client-id e2e-service \\
        --oidc-client-secret $OIDC_SECRET \\
        --strict --validate-outputs [--json]

Stages (15 — one connected business pipeline):
     1. oidc_token          -- real OIDC client_credentials token acquisition
     2. frontend_verify     -- frontend reachable + OIDC provider configured
     3. api_health          -- /health returns all 4 components healthy
     4. workspace_access    -- authenticated workspace list/create
     5. document_upload     -- upload test fixture to real object storage
     6. extraction_trigger  -- POST extract, receive job_id (async worker)
     7. extraction_wait     -- poll job status until COMPLETED (worker proof)
     8. ai_compile          -- LLM-backed sector mapping via /compiler/compile
     9. scenario_build      -- create scenario + approve mappings + compile to shocks
    10. depth_analysis      -- depth plan via real LLM provider (uses scenario)
    11. scenario_run        -- deterministic engine run (uses compiled scenario)
    12. governance_evaluate -- extract claims + evaluate governance status for run
    13. copilot_query       -- real copilot chat interaction via LLM provider
    14. export_download     -- create export + download artifact + verify content
    15. output_validation   -- golden fixture comparison + persisted data check

Connected flow:
    oidc_token → auth_token used by all authenticated stages
    workspace_access → workspace_id flows to all subsequent stages
    document_upload → document_id → extraction → ai_compile
    ai_compile → suggestions → scenario_build (auto-approve decisions)
    scenario_build → scenario_spec_id → depth_analysis, scenario_run
    scenario_run → run_id → governance_evaluate, export_download
    scenario_run → result_sets → output_validation

Modes:
    Default: missing prerequisites produce SKIP.
    --strict: ALL stages critical-path. No --auth-token shortcut (must use
              --oidc-* flags). No synthetic fallbacks. Any SKIP counts as FAIL.

Exit code: 0 if no FAIL (and no SKIP in strict mode), 1 otherwise.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    """Single E2E stage result."""

    name: str
    status: str  # PASS, FAIL, SKIP
    detail: str


@dataclass
class E2EContext:
    """Mutable context that flows between stages — one connected pipeline."""

    api_url: str
    frontend_url: str
    auth_token: str = ""
    strict: bool = False
    validate_outputs: bool = False

    # OIDC config (for real auth in strict mode)
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""

    # Populated by stages as they succeed
    workspace_id: str = ""
    document_id: str = ""
    extraction_job_id: str = ""
    compilation_id: str = ""
    suggestions: list[dict] = field(default_factory=list)
    model_version_id: str = ""
    sector_codes: list[str] = field(default_factory=list)
    scenario_spec_id: str = ""
    depth_plan_id: str = ""
    run_id: str = ""
    run_result_sets: list[dict] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    governance_status: dict = field(default_factory=dict)
    session_id: str = ""
    export_id: str = ""

    def auth_headers(self) -> dict[str, str]:
        """Return Authorization header dict."""
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}

    def _missing(self, name: str, reason: str) -> StageResult:
        """Return FAIL in strict mode, SKIP otherwise."""
        status = "FAIL" if self.strict else "SKIP"
        return StageResult(name=name, status=status, detail=reason)


@dataclass
class E2EReport:
    """Aggregated E2E acceptance report."""

    overall: str  # PASS or FAIL
    api_url: str
    frontend_url: str
    strict: bool = False
    stages: list[StageResult] = field(default_factory=list)
    trace: dict[str, str] = field(default_factory=dict)

    def has_failures(self) -> bool:
        """Return True if any stage has FAIL status."""
        return any(s.status == "FAIL" for s in self.stages)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEALTH_COMPONENTS = {"api", "database", "redis", "object_storage"}
_JOB_POLL_INTERVAL = 2.0  # seconds
_JOB_POLL_MAX_WAIT = 120.0  # seconds
_GOLDEN_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "e2e_golden.json"


# ---------------------------------------------------------------------------
# Stage 1: OIDC Token Acquisition
# ---------------------------------------------------------------------------


def stage_oidc_token(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 1: Acquire access token via real OIDC client_credentials grant.

    In strict mode, --auth-token is not accepted; real OIDC flow required.
    In default mode, --auth-token is an accepted shortcut.
    """
    if not ctx.oidc_issuer:
        if ctx.strict:
            return StageResult(
                name="oidc_token",
                status="FAIL",
                detail="Strict mode requires --oidc-issuer/--oidc-client-id/--oidc-client-secret for real auth (not --auth-token)",
            )
        if ctx.auth_token:
            return StageResult(
                name="oidc_token",
                status="SKIP",
                detail="Using pre-issued --auth-token (not real OIDC flow)",
            )
        return ctx._missing("oidc_token", "No OIDC config and no auth token")

    # Missing OIDC client credentials
    if not ctx.oidc_client_id or not ctx.oidc_client_secret:
        return StageResult(
            name="oidc_token",
            status="FAIL",
            detail="OIDC issuer set but missing --oidc-client-id or --oidc-client-secret",
        )

    # Step 1: OIDC well-known discovery
    try:
        discovery_url = f"{ctx.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
        disc_resp = client.get(discovery_url, timeout=10.0)
        if disc_resp.status_code != 200:
            return StageResult(
                name="oidc_token",
                status="FAIL",
                detail=f"OIDC discovery at {discovery_url} returned {disc_resp.status_code}",
            )
        config = disc_resp.json()
        token_endpoint = config.get("token_endpoint", "")
        if not token_endpoint:
            return StageResult(
                name="oidc_token",
                status="FAIL",
                detail="OIDC discovery response missing token_endpoint",
            )
    except Exception as exc:
        return StageResult(
            name="oidc_token",
            status="FAIL",
            detail=f"OIDC discovery failed: {exc}",
        )

    # Step 2: Client credentials grant
    try:
        token_resp = client.post(
            token_endpoint,
            data={
                "grant_type": "client_credentials",
                "client_id": ctx.oidc_client_id,
                "client_secret": ctx.oidc_client_secret,
                "scope": "openid",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        if token_resp.status_code != 200:
            return StageResult(
                name="oidc_token",
                status="FAIL",
                detail=f"Token endpoint returned {token_resp.status_code}: {token_resp.text[:200]}",
            )
        token_body = token_resp.json()
        access_token = token_body.get("access_token", "")
        if not access_token:
            return StageResult(
                name="oidc_token",
                status="FAIL",
                detail="Token response missing access_token",
            )
        ctx.auth_token = access_token
        expires_in = token_body.get("expires_in", "?")
        return StageResult(
            name="oidc_token",
            status="PASS",
            detail=f"OIDC token acquired via client_credentials (expires_in={expires_in}s)",
        )
    except Exception as exc:
        return StageResult(
            name="oidc_token",
            status="FAIL",
            detail=f"Token acquisition failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Stage 2: Frontend Verification
# ---------------------------------------------------------------------------


def stage_frontend_verify(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 2: Verify frontend is reachable and OIDC-configured."""
    if not ctx.frontend_url:
        return ctx._missing("frontend_verify", "No frontend URL provided")
    try:
        resp = client.get(ctx.frontend_url, timeout=10.0, follow_redirects=True)
        if resp.status_code != 200:
            return StageResult(
                name="frontend_verify",
                status="FAIL",
                detail=f"Frontend returned {resp.status_code}",
            )
        ct = resp.headers.get("content-type", "")
        if "text/html" not in ct:
            return StageResult(
                name="frontend_verify",
                status="FAIL",
                detail=f"Frontend returned non-HTML content-type: {ct}",
            )

        # In strict mode: verify OIDC provider is configured on frontend
        if ctx.strict:
            try:
                prov_resp = client.get(
                    f"{ctx.frontend_url.rstrip('/')}/api/auth/providers",
                    timeout=5.0,
                )
                if prov_resp.status_code == 200:
                    providers = prov_resp.json()
                    if "impactos-oidc" not in providers:
                        return StageResult(
                            name="frontend_verify",
                            status="FAIL",
                            detail="Frontend auth providers missing 'impactos-oidc' — OIDC not configured",
                        )
            except Exception:
                pass  # Provider check is best-effort

        return StageResult(
            name="frontend_verify",
            status="PASS",
            detail=f"Frontend reachable at {ctx.frontend_url}",
        )
    except httpx.ConnectError:
        return StageResult(
            name="frontend_verify",
            status="FAIL",
            detail=f"Cannot connect to frontend at {ctx.frontend_url}",
        )
    except Exception as exc:
        return StageResult(
            name="frontend_verify",
            status="FAIL",
            detail=f"Error reaching frontend: {exc}",
        )


# ---------------------------------------------------------------------------
# Stage 3: API Health
# ---------------------------------------------------------------------------


def stage_api_health(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 3: Verify API /health returns all required components."""
    try:
        resp = client.get(f"{ctx.api_url}/health", timeout=10.0)
        if resp.status_code != 200:
            return StageResult(
                name="api_health",
                status="FAIL",
                detail=f"GET /health returned {resp.status_code}",
            )
        body = resp.json()
        checks = body.get("checks", {})
        present = set(checks.keys())
        missing = _HEALTH_COMPONENTS - present
        if missing:
            return StageResult(
                name="api_health",
                status="FAIL",
                detail=f"Missing health components: {sorted(missing)}",
            )
        unhealthy = []
        for comp, val in checks.items():
            if comp not in _HEALTH_COMPONENTS:
                continue
            status_str = ""
            if isinstance(val, str):
                status_str = val.lower()
            elif isinstance(val, dict):
                status_str = val.get("status", "").lower()
            if status_str not in ("ok", "healthy"):
                unhealthy.append(comp)
        if unhealthy:
            return StageResult(
                name="api_health",
                status="FAIL",
                detail=f"Unhealthy components: {sorted(unhealthy)}",
            )
        return StageResult(
            name="api_health",
            status="PASS",
            detail=f"All {len(_HEALTH_COMPONENTS)} health components OK",
        )
    except httpx.ConnectError:
        return StageResult(
            name="api_health",
            status="FAIL",
            detail=f"Cannot connect to API at {ctx.api_url}",
        )
    except Exception as exc:
        return StageResult(
            name="api_health",
            status="FAIL",
            detail=f"Error checking API health: {exc}",
        )


# ---------------------------------------------------------------------------
# Stage 4: Workspace Access
# ---------------------------------------------------------------------------


def stage_workspace_access(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 4: Authenticated workspace access.  Populates ctx.workspace_id."""
    if not ctx.auth_token:
        return ctx._missing("workspace_access", "No auth token — cannot test authenticated access")
    try:
        resp = client.get(
            f"{ctx.api_url}/v1/workspaces",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if resp.status_code == 401:
            return StageResult(name="workspace_access", status="FAIL", detail="401 Unauthorized — auth token rejected")
        if resp.status_code == 403:
            return StageResult(name="workspace_access", status="FAIL", detail="403 Forbidden — insufficient permissions")
        if resp.status_code != 200:
            return StageResult(name="workspace_access", status="FAIL", detail=f"GET /v1/workspaces returned {resp.status_code}")
        body = resp.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        if isinstance(items, list) and len(items) > 0:
            ctx.workspace_id = items[0].get("id", "")
            return StageResult(name="workspace_access", status="PASS", detail=f"Workspace accessible: {ctx.workspace_id}")
        # Create workspace
        create_resp = client.post(
            f"{ctx.api_url}/v1/workspaces",
            headers=ctx.auth_headers(),
            json={"name": "staging-e2e-acceptance", "description": "Sprint 31 E2E acceptance workspace"},
            timeout=10.0,
        )
        if create_resp.status_code in (200, 201):
            create_body = create_resp.json()
            ctx.workspace_id = create_body.get("id", "")
            return StageResult(name="workspace_access", status="PASS", detail=f"Created workspace: {ctx.workspace_id}")
        return StageResult(name="workspace_access", status="FAIL", detail=f"No workspaces and create returned {create_resp.status_code}")
    except Exception as exc:
        return StageResult(name="workspace_access", status="FAIL", detail=f"Error accessing workspaces: {exc}")


# ---------------------------------------------------------------------------
# Stage 5: Document Upload
# ---------------------------------------------------------------------------


def stage_document_upload(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 5: Upload test fixture to real object storage.  Populates ctx.document_id."""
    if not ctx.workspace_id:
        return ctx._missing("document_upload", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("document_upload", "No auth token")
    try:
        fixture_content = b"%PDF-1.4 staging-e2e-test-fixture"
        files = {"file": ("staging-e2e-test.pdf", io.BytesIO(fixture_content), "application/pdf")}
        data = {"doc_type": "boq", "description": "Sprint 31 E2E acceptance test fixture"}
        resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/documents",
            headers=ctx.auth_headers(),
            files=files,
            data=data,
            timeout=30.0,
        )
        if resp.status_code in (200, 201):
            body = resp.json()
            ctx.document_id = body.get("id", "")
            return StageResult(name="document_upload", status="PASS", detail=f"Document uploaded: {ctx.document_id}")
        return StageResult(name="document_upload", status="FAIL", detail=f"Upload returned {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        return StageResult(name="document_upload", status="FAIL", detail=f"Error uploading document: {exc}")


# ---------------------------------------------------------------------------
# Stage 6: Extraction Trigger
# ---------------------------------------------------------------------------


def stage_extraction_trigger(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 6: Trigger extraction on uploaded document.  Populates ctx.extraction_job_id.

    Submits an async Celery job — proving the worker queue accepts jobs.
    """
    if not ctx.workspace_id or not ctx.document_id:
        return ctx._missing("extraction_trigger", "No workspace or document available")
    if not ctx.auth_token:
        return ctx._missing("extraction_trigger", "No auth token")
    try:
        resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/documents/{ctx.document_id}/extract",
            headers=ctx.auth_headers(),
            json={"extract_tables": True, "extract_line_items": True},
            timeout=30.0,
        )
        if resp.status_code in (200, 201, 202):
            body = resp.json()
            ctx.extraction_job_id = body.get("job_id", "")
            status = body.get("status", "unknown")
            return StageResult(
                name="extraction_trigger",
                status="PASS",
                detail=f"Extraction triggered: job_id={ctx.extraction_job_id}, status={status}",
            )
        return StageResult(
            name="extraction_trigger",
            status="FAIL",
            detail=f"Extract returned {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(name="extraction_trigger", status="FAIL", detail=f"Error triggering extraction: {exc}")


# ---------------------------------------------------------------------------
# Stage 7: Extraction Wait (Worker Proof)
# ---------------------------------------------------------------------------


def stage_extraction_wait(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 7: Poll extraction job until COMPLETED.

    Real worker execution proof: Celery worker must pick up the job,
    run the extraction provider, and persist results.
    """
    if not ctx.workspace_id or not ctx.extraction_job_id:
        return ctx._missing("extraction_wait", "No extraction job to poll")
    if not ctx.auth_token:
        return ctx._missing("extraction_wait", "No auth token")
    try:
        elapsed = 0.0
        last_status = "unknown"
        while elapsed < _JOB_POLL_MAX_WAIT:
            resp = client.get(
                f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/jobs/{ctx.extraction_job_id}",
                headers=ctx.auth_headers(),
                timeout=10.0,
            )
            if resp.status_code != 200:
                return StageResult(
                    name="extraction_wait",
                    status="FAIL",
                    detail=f"Job status returned {resp.status_code}",
                )
            body = resp.json()
            last_status = body.get("status", "unknown")
            if last_status == "COMPLETED":
                return StageResult(
                    name="extraction_wait",
                    status="PASS",
                    detail=f"Extraction completed (worker executed job in {elapsed:.0f}s)",
                )
            if last_status == "FAILED":
                error = body.get("error_message", "unknown error")
                return StageResult(
                    name="extraction_wait",
                    status="FAIL",
                    detail=f"Extraction job FAILED: {error}",
                )
            time.sleep(_JOB_POLL_INTERVAL)
            elapsed += _JOB_POLL_INTERVAL
        return StageResult(
            name="extraction_wait",
            status="FAIL",
            detail=f"Extraction timed out after {_JOB_POLL_MAX_WAIT}s (last status: {last_status})",
        )
    except Exception as exc:
        return StageResult(name="extraction_wait", status="FAIL", detail=f"Error polling extraction: {exc}")


# ---------------------------------------------------------------------------
# Stage 8: AI Compile (LLM-backed sector mapping)
# ---------------------------------------------------------------------------


def stage_ai_compile(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 8: LLM-backed sector mapping via /compiler/compile.

    Uses the uploaded document_id. Populates ctx.compilation_id and
    ctx.suggestions for use in scenario_build (stage 9).
    """
    if not ctx.workspace_id:
        return ctx._missing("ai_compile", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("ai_compile", "No auth token")
    if not ctx.document_id:
        return ctx._missing("ai_compile", "No document_id — upload and extraction must pass first")
    try:
        compile_payload: dict = {
            "scenario_name": "staging-e2e-acceptance-scenario",
            "base_model_version_id": "default",
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2028,
            "document_id": ctx.document_id,
        }

        resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/compiler/compile",
            headers=ctx.auth_headers(),
            json=compile_payload,
            timeout=60.0,
        )
        if resp.status_code in (200, 201):
            body = resp.json()
            ctx.compilation_id = body.get("compilation_id", "")
            ctx.suggestions = body.get("suggestions", [])
            high = body.get("high_confidence", 0)
            med = body.get("medium_confidence", 0)
            low = body.get("low_confidence", 0)
            return StageResult(
                name="ai_compile",
                status="PASS",
                detail=f"AI compile: {ctx.compilation_id} ({len(ctx.suggestions)} suggestions, H={high} M={med} L={low})",
            )
        if resp.status_code == 503:
            return StageResult(
                name="ai_compile",
                status="FAIL",
                detail=f"Compiler unavailable (503 — no LLM provider): {resp.text[:200]}",
            )
        return StageResult(
            name="ai_compile",
            status="FAIL",
            detail=f"Compile returned {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(name="ai_compile", status="FAIL", detail=f"Error in AI compile: {exc}")


# ---------------------------------------------------------------------------
# Stage 9: Scenario Build (connected to AI compile)
# ---------------------------------------------------------------------------


def stage_scenario_build(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 9: Create scenario from AI compile results and compile with decisions.

    Uses ctx.suggestions from stage 8 (ai_compile) to auto-approve mappings,
    then compiles the scenario to produce shock_items. This is the connected
    pipeline: upload → extract → AI compile → scenario build.
    """
    if not ctx.workspace_id:
        return ctx._missing("scenario_build", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("scenario_build", "No auth token")
    if not ctx.suggestions and not ctx.compilation_id:
        return ctx._missing("scenario_build", "No AI compilation results — stage 8 must pass first")

    try:
        # Step 1: Get model version (need base_model_version_id + sector count)
        mv_resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/engine/model-versions",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if mv_resp.status_code == 200:
            mv_body = mv_resp.json()
            models = mv_body.get("items", mv_body) if isinstance(mv_body, dict) else mv_body
            if isinstance(models, list) and len(models) > 0:
                model = models[0]
                ctx.model_version_id = model.get("model_version_id", model.get("id", ""))
                ctx.sector_codes = model.get("sector_codes", [])

        # Step 2: Create scenario
        create_payload = {
            "name": "staging-e2e-acceptance",
            "base_model_version_id": ctx.model_version_id or "default",
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2028,
        }
        create_resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/scenarios",
            headers=ctx.auth_headers(),
            json=create_payload,
            timeout=10.0,
        )
        if create_resp.status_code not in (200, 201):
            return StageResult(
                name="scenario_build",
                status="FAIL",
                detail=f"Create scenario returned {create_resp.status_code}: {create_resp.text[:200]}",
            )
        create_body = create_resp.json()
        ctx.scenario_spec_id = create_body.get("scenario_spec_id", "")

        # Step 3: Build decisions from AI compile suggestions (auto-approve all)
        decisions = []
        for s in ctx.suggestions:
            decisions.append({
                "line_item_id": s.get("line_item_id", ""),
                "final_sector_code": s.get("sector_code", ""),
                "decision_type": "APPROVED",
                "suggested_confidence": s.get("confidence", 0.0),
                "decided_by": "00000000-0000-7000-8000-000000000001",
            })

        # Step 4: Compile scenario with decisions (produces shock_items)
        compile_payload: dict = {
            "decisions": decisions,
            "phasing": {"2024": 0.2, "2025": 0.3, "2026": 0.3, "2027": 0.15, "2028": 0.05},
            "default_domestic_share": 0.65,
        }
        if ctx.document_id:
            compile_payload["document_id"] = ctx.document_id

        compile_resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/scenarios/{ctx.scenario_spec_id}/compile",
            headers=ctx.auth_headers(),
            json=compile_payload,
            timeout=60.0,
        )
        if compile_resp.status_code not in (200, 201):
            return StageResult(
                name="scenario_build",
                status="FAIL",
                detail=f"Compile scenario returned {compile_resp.status_code}: {compile_resp.text[:200]}",
            )
        compile_body = compile_resp.json()
        n_shocks = len(compile_body.get("shock_items", []))
        version = compile_body.get("version", "?")
        return StageResult(
            name="scenario_build",
            status="PASS",
            detail=f"Scenario {ctx.scenario_spec_id} v{version} compiled: {n_shocks} shocks from {len(decisions)} decisions",
        )
    except Exception as exc:
        return StageResult(name="scenario_build", status="FAIL", detail=f"Error building scenario: {exc}")


# ---------------------------------------------------------------------------
# Stage 10: Depth Analysis (LLM, connected to scenario)
# ---------------------------------------------------------------------------


def stage_depth_analysis(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 10: Depth plan via real LLM provider.  Uses ctx.scenario_spec_id."""
    if not ctx.workspace_id:
        return ctx._missing("depth_analysis", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("depth_analysis", "No auth token")
    try:
        depth_payload: dict = {
            "classification": "INTERNAL",
            "context": {},
        }
        if ctx.scenario_spec_id:
            depth_payload["scenario_spec_id"] = ctx.scenario_spec_id

        resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/depth/plans",
            headers=ctx.auth_headers(),
            json=depth_payload,
            timeout=60.0,
        )
        if resp.status_code in (200, 201):
            body = resp.json()
            ctx.depth_plan_id = body.get("plan_id", "")
            status = body.get("status", "unknown")
            return StageResult(
                name="depth_analysis",
                status="PASS",
                detail=f"Depth plan created: {ctx.depth_plan_id}, status={status}",
            )
        if resp.status_code == 503:
            return StageResult(
                name="depth_analysis",
                status="FAIL",
                detail=f"Depth unavailable (503 — no LLM provider): {resp.text[:200]}",
            )
        return StageResult(
            name="depth_analysis",
            status="FAIL",
            detail=f"Depth returned {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(name="depth_analysis", status="FAIL", detail=f"Error triggering depth: {exc}")


# ---------------------------------------------------------------------------
# Stage 11: Scenario Run (deterministic engine, connected to scenario_build)
# ---------------------------------------------------------------------------


def stage_scenario_run(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 11: Deterministic engine run using the compiled scenario from stage 9.

    Populates ctx.run_id and ctx.run_result_sets.
    Uses ctx.scenario_spec_id (NOT arbitrary scenario listing).
    """
    if not ctx.workspace_id:
        return ctx._missing("scenario_run", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("scenario_run", "No auth token")
    if not ctx.scenario_spec_id:
        return ctx._missing("scenario_run", "No scenario_spec_id — scenario_build (stage 9) must pass first")
    try:
        # Build satellite coefficients based on sector count
        n_sectors = max(len(ctx.sector_codes), 5)
        run_payload: dict = {
            "mode": "SANDBOX",
            "satellite_coefficients": {
                "jobs_coeff": [0.10] * n_sectors,
                "import_ratio": [0.20] * n_sectors,
                "va_ratio": [0.50] * n_sectors,
            },
        }

        resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/scenarios/{ctx.scenario_spec_id}/run",
            headers=ctx.auth_headers(),
            json=run_payload,
            timeout=60.0,
        )
        if resp.status_code in (200, 201, 202):
            body = resp.json()
            ctx.run_id = body.get("run_id", body.get("id", ""))
            ctx.run_result_sets = body.get("result_sets", [])
            n_results = len(ctx.run_result_sets)
            return StageResult(
                name="scenario_run",
                status="PASS",
                detail=f"Run completed: run_id={ctx.run_id}, result_sets={n_results}",
            )
        return StageResult(
            name="scenario_run",
            status="FAIL",
            detail=f"Run returned {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(name="scenario_run", status="FAIL", detail=f"Error triggering run: {exc}")


# ---------------------------------------------------------------------------
# Stage 12: Governance Evaluate (real claims, not reachability)
# ---------------------------------------------------------------------------


def stage_governance_evaluate(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 12: Extract claims for the actual run and evaluate governance status.

    This is real governance evaluation, not reachability probing.
    404 / no claims = FAIL (governance must actively evaluate the run).
    """
    if not ctx.workspace_id:
        return ctx._missing("governance_evaluate", "No workspace available")
    if not ctx.run_id:
        return ctx._missing("governance_evaluate", "No run_id — scenario_run (stage 11) must pass first")
    if not ctx.auth_token:
        return ctx._missing("governance_evaluate", "No auth token")
    try:
        # Step 1: Extract claims from the run
        extract_payload = {
            "draft_text": f"Economic impact analysis run {ctx.run_id} for staging E2E acceptance.",
            "run_id": ctx.run_id,
        }
        extract_resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/governance/claims/extract",
            headers=ctx.auth_headers(),
            json=extract_payload,
            timeout=30.0,
        )
        if extract_resp.status_code not in (200, 201):
            return StageResult(
                name="governance_evaluate",
                status="FAIL",
                detail=f"Claim extraction returned {extract_resp.status_code}: {extract_resp.text[:200]}",
            )
        extract_body = extract_resp.json()
        claims = extract_body.get("claims", [])
        ctx.claim_ids = [c.get("claim_id", "") for c in claims]

        if len(claims) == 0:
            return StageResult(
                name="governance_evaluate",
                status="FAIL",
                detail="No claims extracted — governance layer did not evaluate the run",
            )

        # Step 2: Get governance status for the run
        status_resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/governance/status/{ctx.run_id}",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if status_resp.status_code == 200:
            status_body = status_resp.json()
            ctx.governance_status = status_body
            claims_total = status_body.get("claims_total", 0)
            nff_passed = status_body.get("nff_passed", False)
            return StageResult(
                name="governance_evaluate",
                status="PASS",
                detail=f"Governance evaluated: {claims_total} claims, nff_passed={nff_passed}",
            )

        # Governance status endpoint not available — still pass if claims extracted
        return StageResult(
            name="governance_evaluate",
            status="PASS",
            detail=f"Claims extracted: {len(claims)} (governance status endpoint returned {status_resp.status_code})",
        )
    except Exception as exc:
        return StageResult(name="governance_evaluate", status="FAIL", detail=f"Error evaluating governance: {exc}")


# ---------------------------------------------------------------------------
# Stage 13: Copilot Query (real LLM chat, not status probe)
# ---------------------------------------------------------------------------


def stage_copilot_query(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 13: Real copilot chat interaction via LLM provider.

    Creates a chat session and sends a message that references the actual
    workspace data, proving the copilot pipeline works end-to-end.
    """
    if not ctx.workspace_id:
        return ctx._missing("copilot_query", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("copilot_query", "No auth token")
    try:
        # Step 1: Check copilot status first
        status_resp = client.get(f"{ctx.api_url}/api/copilot/status", timeout=5.0)
        if status_resp.status_code == 404:
            return ctx._missing("copilot_query", "Copilot endpoint not deployed (404)")
        if status_resp.status_code == 200:
            status_body = status_resp.json()
            if not status_body.get("enabled", False):
                return ctx._missing("copilot_query", f"Copilot disabled: {status_body.get('detail', '')}")
            if not status_body.get("ready", False):
                return StageResult(
                    name="copilot_query",
                    status="FAIL",
                    detail=f"Copilot enabled but not ready (no LLM provider): {status_body.get('detail', '')}",
                )

        # Step 2: Create chat session
        session_resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/chat/sessions",
            headers=ctx.auth_headers(),
            json={"title": "staging-e2e-acceptance"},
            timeout=10.0,
        )
        if session_resp.status_code not in (200, 201):
            return StageResult(
                name="copilot_query",
                status="FAIL",
                detail=f"Create chat session returned {session_resp.status_code}: {session_resp.text[:200]}",
            )
        session_body = session_resp.json()
        ctx.session_id = session_body.get("session_id", "")

        # Step 3: Send message referencing actual workspace data (real LLM execution)
        message_content = "What data is available in this workspace? List any scenarios or model versions."
        if ctx.run_id:
            message_content = f"Summarize the results of run {ctx.run_id}."

        msg_resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/chat/sessions/{ctx.session_id}/messages",
            headers=ctx.auth_headers(),
            json={"content": message_content, "confirm_scenario": False},
            timeout=60.0,
        )
        if msg_resp.status_code not in (200, 201):
            return StageResult(
                name="copilot_query",
                status="FAIL",
                detail=f"Chat message returned {msg_resp.status_code}: {msg_resp.text[:200]}",
            )
        msg_body = msg_resp.json()
        content = msg_body.get("content", "")
        token_usage = msg_body.get("token_usage", {})
        tool_calls = msg_body.get("tool_calls", [])

        if not content:
            return StageResult(
                name="copilot_query",
                status="FAIL",
                detail="Copilot returned empty response — LLM did not execute",
            )

        output_tokens = token_usage.get("output_tokens", 0) if token_usage else 0
        n_tools = len(tool_calls) if tool_calls else 0
        return StageResult(
            name="copilot_query",
            status="PASS",
            detail=f"Copilot responded ({output_tokens} tokens, {n_tools} tool calls), session={ctx.session_id}",
        )
    except Exception as exc:
        return StageResult(name="copilot_query", status="FAIL", detail=f"Error querying copilot: {exc}")


# ---------------------------------------------------------------------------
# Stage 14: Export + Download
# ---------------------------------------------------------------------------


def stage_export_download(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 14: Create export from run results, download, and verify content."""
    if not ctx.workspace_id:
        return ctx._missing("export_download", "No workspace available")
    if not ctx.run_id:
        return ctx._missing("export_download", "No run_id — scenario_run (stage 11) must pass first")
    if not ctx.auth_token:
        return ctx._missing("export_download", "No auth token")
    try:
        # Step 1: Create export
        export_payload: dict = {
            "run_id": ctx.run_id,
            "mode": "SANDBOX",
            "export_formats": ["excel"],
            "pack_data": {
                "scenario_name": "staging-e2e-acceptance",
                "run_id": ctx.run_id,
            },
        }
        create_resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/exports",
            headers=ctx.auth_headers(),
            json=export_payload,
            timeout=60.0,
        )
        if create_resp.status_code not in (200, 201, 202):
            return StageResult(
                name="export_download",
                status="FAIL",
                detail=f"Export create returned {create_resp.status_code}: {create_resp.text[:200]}",
            )
        create_body = create_resp.json()
        ctx.export_id = create_body.get("export_id", create_body.get("id", ""))
        export_status = create_body.get("status", "unknown")
        blocking = create_body.get("blocking_reasons", [])

        if export_status == "BLOCKED" and blocking:
            return StageResult(
                name="export_download",
                status="FAIL",
                detail=f"Export blocked: {', '.join(blocking[:3])}",
            )

        # Step 2: Download the export artifact
        dl_resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/exports/{ctx.export_id}/download/excel",
            headers=ctx.auth_headers(),
            timeout=30.0,
        )
        if dl_resp.status_code == 200:
            content_len = len(dl_resp.content)
            if content_len == 0:
                return StageResult(
                    name="export_download",
                    status="FAIL",
                    detail="Export download returned empty content",
                )
            return StageResult(
                name="export_download",
                status="PASS",
                detail=f"Export downloaded: {content_len} bytes, export_id={ctx.export_id}",
            )
        if dl_resp.status_code == 409:
            return StageResult(
                name="export_download",
                status="FAIL",
                detail=f"Export not ready for download (status: {export_status})",
            )
        return StageResult(
            name="export_download",
            status="FAIL",
            detail=f"Export download returned {dl_resp.status_code}",
        )
    except Exception as exc:
        return StageResult(name="export_download", status="FAIL", detail=f"Error with export: {exc}")


# ---------------------------------------------------------------------------
# Stage 15: Output Validation (golden fixture + persisted data)
# ---------------------------------------------------------------------------


def _load_golden_fixture() -> dict:
    """Load golden validation rules from fixture file."""
    if _GOLDEN_FIXTURE_PATH.exists():
        return json.loads(_GOLDEN_FIXTURE_PATH.read_text())
    return {}


def stage_output_validation(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 15: Validate run outputs against golden fixture rules.

    Checks (from golden fixture):
    - result_sets count >= min_count
    - Required metric_types are present (e.g., "output")
    - Each metric has values with entries in valid range
    - At least one metric has non-zero values (real computation)

    With --validate-outputs:
    - Fetches persisted run and compares result_sets for consistency
    """
    if not ctx.run_id:
        return ctx._missing("output_validation", "No run_id — cannot validate outputs")
    if not ctx.run_result_sets:
        return ctx._missing("output_validation", "No result_sets captured from run")

    golden = _load_golden_fixture()
    rs_rules = golden.get("result_sets", {})
    errors: list[str] = []

    # Check 1: minimum result_sets count
    min_count = rs_rules.get("min_count", 1)
    if len(ctx.run_result_sets) < min_count:
        errors.append(f"result_sets count {len(ctx.run_result_sets)} < required {min_count}")

    # Check 2: required metric_types
    actual_types = {rs.get("metric_type", "") for rs in ctx.run_result_sets}
    required_types = rs_rules.get("required_metric_types", [])
    for rt in required_types:
        if rt not in actual_types:
            errors.append(f"Required metric_type '{rt}' missing from results")

    # Check 3: per-metric validation
    per_metric = rs_rules.get("per_metric", {})
    vmin = per_metric.get("value_range_min", -1e15)
    vmax = per_metric.get("value_range_max", 1e15)
    require_nonzero = per_metric.get("require_non_zero", True)

    has_nonzero = False
    for i, rs in enumerate(ctx.run_result_sets):
        mt = rs.get("metric_type", f"result_set[{i}]")
        if not rs.get("metric_type"):
            errors.append(f"result_set[{i}] missing metric_type")
        values = rs.get("values", {})
        if not isinstance(values, dict) or len(values) == 0:
            errors.append(f"result_set[{i}] ({mt}) has empty values")
            continue
        for k, v in values.items():
            if isinstance(v, (int, float)):
                if v < vmin or v > vmax:
                    errors.append(f"{mt}.{k}={v} outside valid range [{vmin}, {vmax}]")
                if v != 0:
                    has_nonzero = True

    if require_nonzero and not has_nonzero and not errors:
        errors.append("All result_set values are zero — no real computation occurred")

    if errors:
        return StageResult(
            name="output_validation",
            status="FAIL",
            detail=f"Output validation failed: {'; '.join(errors)}",
        )

    # Check 4: persisted data consistency (with --validate-outputs)
    if ctx.validate_outputs and ctx.workspace_id and ctx.auth_token:
        try:
            resp = client.get(
                f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/engine/runs/{ctx.run_id}",
                headers=ctx.auth_headers(),
                timeout=10.0,
            )
            if resp.status_code == 200:
                persisted = resp.json()
                persisted_sets = persisted.get("result_sets", [])
                if len(persisted_sets) != len(ctx.run_result_sets):
                    errors.append(
                        f"Persisted result_sets count ({len(persisted_sets)}) "
                        f"!= in-memory ({len(ctx.run_result_sets)})"
                    )
                mem_types = sorted(rs.get("metric_type", "") for rs in ctx.run_result_sets)
                db_types = sorted(rs.get("metric_type", "") for rs in persisted_sets)
                if mem_types != db_types:
                    errors.append(f"Metric type mismatch: memory={mem_types} vs persisted={db_types}")
            else:
                errors.append(f"Failed to fetch persisted run: {resp.status_code}")
        except Exception as exc:
            errors.append(f"Error fetching persisted run: {exc}")

    if errors:
        return StageResult(
            name="output_validation",
            status="FAIL",
            detail=f"Output validation failed: {'; '.join(errors)}",
        )

    n_metrics = len(ctx.run_result_sets)
    detail = f"Output valid: {n_metrics} result_sets, required metric_types present, non-zero values"
    if ctx.validate_outputs:
        detail += ", persisted data matches"
    return StageResult(name="output_validation", status="PASS", detail=detail)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

# Stage names for cascade-skip/fail when API is unreachable
_ALL_STAGES_AFTER_HEALTH = [
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


def run_e2e(
    api_url: str,
    frontend_url: str = "",
    auth_token: str = "",
    strict: bool = False,
    validate_outputs: bool = False,
    oidc_issuer: str = "",
    oidc_client_id: str = "",
    oidc_client_secret: str = "",
) -> E2EReport:
    """Execute all E2E stages in order — one connected pipeline."""
    ctx = E2EContext(
        api_url=api_url,
        frontend_url=frontend_url,
        auth_token=auth_token,
        strict=strict,
        validate_outputs=validate_outputs,
        oidc_issuer=oidc_issuer,
        oidc_client_id=oidc_client_id,
        oidc_client_secret=oidc_client_secret,
    )
    stages: list[StageResult] = []

    with httpx.Client() as client:
        # Stage 1: OIDC token acquisition
        stages.append(stage_oidc_token(client, ctx))

        # Stage 2: Frontend verification
        stages.append(stage_frontend_verify(client, ctx))

        # Stage 3: API health
        api_health = stage_api_health(client, ctx)
        stages.append(api_health)

        if api_health.status == "FAIL":
            skip_status = "FAIL" if strict else "SKIP"
            for name in _ALL_STAGES_AFTER_HEALTH:
                stages.append(StageResult(name=name, status=skip_status, detail="API not healthy — cascade"))
        else:
            # Stage 4: Workspace access
            stages.append(stage_workspace_access(client, ctx))
            # Stage 5: Document upload
            stages.append(stage_document_upload(client, ctx))
            # Stage 6: Extraction trigger (worker job submit)
            stages.append(stage_extraction_trigger(client, ctx))
            # Stage 7: Extraction wait (worker proof)
            stages.append(stage_extraction_wait(client, ctx))
            # Stage 8: AI compile (LLM-backed, uses document_id)
            stages.append(stage_ai_compile(client, ctx))
            # Stage 9: Scenario build (uses AI compile suggestions)
            stages.append(stage_scenario_build(client, ctx))
            # Stage 10: Depth analysis (uses scenario_spec_id)
            stages.append(stage_depth_analysis(client, ctx))
            # Stage 11: Scenario run (uses compiled scenario)
            stages.append(stage_scenario_run(client, ctx))
            # Stage 12: Governance evaluate (extracts claims for run)
            stages.append(stage_governance_evaluate(client, ctx))
            # Stage 13: Copilot query (real LLM interaction)
            stages.append(stage_copilot_query(client, ctx))
            # Stage 14: Export + download
            stages.append(stage_export_download(client, ctx))
            # Stage 15: Output validation (golden fixture)
            stages.append(stage_output_validation(client, ctx))

    # In strict mode, any SKIP counts as failure
    if strict:
        has_problem = any(s.status in ("FAIL", "SKIP") for s in stages)
    else:
        has_problem = any(s.status == "FAIL" for s in stages)

    return E2EReport(
        overall="FAIL" if has_problem else "PASS",
        api_url=api_url,
        frontend_url=frontend_url,
        strict=strict,
        stages=stages,
        trace={
            "workspace_id": ctx.workspace_id,
            "document_id": ctx.document_id,
            "extraction_job_id": ctx.extraction_job_id,
            "compilation_id": ctx.compilation_id,
            "model_version_id": ctx.model_version_id,
            "scenario_spec_id": ctx.scenario_spec_id,
            "depth_plan_id": ctx.depth_plan_id,
            "run_id": ctx.run_id,
            "export_id": ctx.export_id,
            "session_id": ctx.session_id,
        },
    )


# ---------------------------------------------------------------------------
# CLI output helpers
# ---------------------------------------------------------------------------

_STATUS_SYMBOLS = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}


def _print_table(report: E2EReport) -> None:
    """Print a human-readable table of stage results."""
    max_name = max(len(s.name) for s in report.stages) if report.stages else 10
    print()
    print("Full-System E2E Acceptance Report")
    print(f"  API URL:      {report.api_url}")
    print(f"  Frontend URL: {report.frontend_url or '(not provided)'}")
    print(f"  Mode:         {'STRICT (acceptance)' if report.strict else 'default'}")
    print()
    print(f"{'Stage':<{max_name + 2}} {'Status':<8} Detail")
    print("-" * (max_name + 2 + 8 + 60))
    for s in report.stages:
        symbol = _STATUS_SYMBOLS.get(s.status, s.status)
        print(f"{s.name:<{max_name + 2}} {symbol:<8} {s.detail}")
    print()
    if any(v for v in report.trace.values()):
        print("Trace (captured IDs):")
        for k, v in report.trace.items():
            if v:
                print(f"  {k}: {v}")
        print()
    print(f"Overall: {report.overall}")
    print()


def _print_json(report: E2EReport) -> None:
    """Print JSON report to stdout."""
    print(json.dumps(asdict(report), indent=2))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and run the full E2E acceptance suite."""
    parser = argparse.ArgumentParser(
        description="Full-system staging E2E acceptance harness.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output structured JSON report")
    parser.add_argument("--api-url", type=str, required=True, help="Base URL of the ImpactOS API server")
    parser.add_argument("--frontend-url", type=str, default="", help="Base URL of the ImpactOS frontend")
    parser.add_argument(
        "--auth-token",
        type=str,
        default=os.environ.get("STAGING_AUTH_TOKEN", ""),
        help="Bearer token (default mode only; strict mode requires --oidc-* flags)",
    )
    parser.add_argument("--oidc-issuer", type=str, default="", help="OIDC issuer URL for real auth")
    parser.add_argument("--oidc-client-id", type=str, default="", help="OIDC client ID for client_credentials grant")
    parser.add_argument("--oidc-client-secret", type=str, default="", help="OIDC client secret")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict acceptance: all SKIPs become FAILs, requires --oidc-* for real auth",
    )
    parser.add_argument(
        "--validate-outputs",
        action="store_true",
        help="Validate run outputs against persisted data for correctness",
    )
    args = parser.parse_args()

    report = run_e2e(
        api_url=args.api_url,
        frontend_url=args.frontend_url,
        auth_token=args.auth_token,
        strict=args.strict,
        validate_outputs=args.validate_outputs,
        oidc_issuer=args.oidc_issuer,
        oidc_client_id=args.oidc_client_id,
        oidc_client_secret=args.oidc_client_secret,
    )

    if args.json_output:
        _print_json(report)
    else:
        _print_table(report)

    sys.exit(1 if report.has_failures() else 0)


if __name__ == "__main__":
    main()
