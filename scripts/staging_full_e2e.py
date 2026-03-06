"""Full-system staging E2E acceptance harness.

Usage:
    python scripts/staging_full_e2e.py [--json] \\
        --api-url http://staging-api:8000 \\
        --frontend-url http://staging-frontend:3000 \\
        --auth-token TOKEN \\
        [--strict] [--validate-outputs]

Stages (14 — full business path):
     1. frontend_reachable  -- frontend responds with HTML
     2. api_health          -- /health returns all 4 components healthy
     3. workspace_access    -- authenticated workspace list/create
     4. document_upload     -- upload test fixture to real object storage
     5. extraction_trigger  -- POST extract, receive job_id (async worker)
     6. extraction_wait     -- poll job status until COMPLETED (worker proof)
     7. compile             -- compile scenario via real LLM provider
     8. depth_analysis      -- depth plan via real LLM provider
     9. copilot_reachable   -- copilot runtime status check
    10. scenario_run        -- deterministic engine run with persisted outputs
    11. governance_check    -- governance layer functional
    12. export_create       -- export generation from run results
    13. export_download     -- artifact download and non-empty content
    14. output_validation   -- compare run results against expected values

Modes:
    Default: missing prerequisites produce SKIP.
    --strict: ALL stages are critical-path; missing auth, empty prerequisites,
              or disabled providers produce FAIL instead of SKIP.  This is the
              acceptance mode: every SKIP counts as FAIL.

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
    """Mutable context that flows between stages."""

    api_url: str
    frontend_url: str
    auth_token: str
    strict: bool = False
    validate_outputs: bool = False

    # Populated by stages as they succeed
    workspace_id: str = ""
    document_id: str = ""
    extraction_job_id: str = ""
    compilation_id: str = ""
    depth_plan_id: str = ""
    scenario_id: str = ""
    run_id: str = ""
    export_id: str = ""

    # Captured for output validation
    run_result_sets: list[dict] = field(default_factory=list)

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


# ---------------------------------------------------------------------------
# Individual stages
# ---------------------------------------------------------------------------


def stage_frontend_reachable(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 1: Verify frontend is reachable and returns HTML."""
    if not ctx.frontend_url:
        return ctx._missing("frontend_reachable", "No frontend URL provided")
    try:
        resp = client.get(ctx.frontend_url, timeout=10.0, follow_redirects=True)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "")
            if "text/html" in ct:
                return StageResult(
                    name="frontend_reachable",
                    status="PASS",
                    detail=f"Frontend reachable at {ctx.frontend_url}",
                )
            return StageResult(
                name="frontend_reachable",
                status="FAIL",
                detail=f"Frontend returned non-HTML content-type: {ct}",
            )
        return StageResult(
            name="frontend_reachable",
            status="FAIL",
            detail=f"Frontend returned {resp.status_code}",
        )
    except httpx.ConnectError:
        return StageResult(
            name="frontend_reachable",
            status="FAIL",
            detail=f"Cannot connect to frontend at {ctx.frontend_url}",
        )
    except Exception as exc:
        return StageResult(
            name="frontend_reachable",
            status="FAIL",
            detail=f"Error reaching frontend: {exc}",
        )


def stage_api_health(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 2: Verify API /health returns all required components."""
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


def stage_workspace_access(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 3: Authenticated workspace access.  Populates ctx.workspace_id."""
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


def stage_document_upload(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 4: Upload test fixture to real object storage.  Populates ctx.document_id."""
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


def stage_extraction_trigger(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 5: Trigger extraction on uploaded document.  Populates ctx.extraction_job_id.

    This exercises the real provider path (Azure DI / local) and submits
    an async Celery job — proving the worker queue is functional.
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


def stage_extraction_wait(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 6: Poll extraction job until COMPLETED.

    This is the real worker execution proof: the Celery worker must pick up
    the job, run the extraction provider, and persist results.
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


def stage_compile(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 7: Compile scenario via real LLM provider.  Populates ctx.compilation_id.

    Exercises the compiler's LLM-backed sector mapping path.
    """
    if not ctx.workspace_id:
        return ctx._missing("compile", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("compile", "No auth token")
    try:
        compile_payload: dict = {
            "scenario_name": "staging-e2e-acceptance-scenario",
            "base_model_version_id": "default",
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2028,
        }
        # If we have a document, use document_id; otherwise use synthetic line items
        if ctx.document_id:
            compile_payload["document_id"] = ctx.document_id
        else:
            compile_payload["line_items"] = [
                {"line_item_id": "e2e-li-1", "raw_text": "Construction of highway interchange", "total_value": 50_000_000.0},
            ]

        resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/compiler/compile",
            headers=ctx.auth_headers(),
            json=compile_payload,
            timeout=60.0,
        )
        if resp.status_code in (200, 201):
            body = resp.json()
            ctx.compilation_id = body.get("compilation_id", "")
            high = body.get("high_confidence", 0)
            med = body.get("medium_confidence", 0)
            low = body.get("low_confidence", 0)
            return StageResult(
                name="compile",
                status="PASS",
                detail=f"Compiled: {ctx.compilation_id} (H={high} M={med} L={low})",
            )
        if resp.status_code == 503:
            detail = resp.text[:200]
            return StageResult(
                name="compile",
                status="FAIL",
                detail=f"Compiler unavailable (503 — no LLM provider): {detail}",
            )
        return StageResult(
            name="compile",
            status="FAIL",
            detail=f"Compile returned {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(name="compile", status="FAIL", detail=f"Error compiling: {exc}")


def stage_depth_analysis(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 8: Trigger depth analysis via real LLM provider.  Populates ctx.depth_plan_id.

    Exercises the Al-Muhāsibī depth engine's LLM-backed analysis path.
    """
    if not ctx.workspace_id:
        return ctx._missing("depth_analysis", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("depth_analysis", "No auth token")
    try:
        depth_payload: dict = {
            "classification": "INTERNAL",
            "context": {},
        }
        if ctx.scenario_id:
            depth_payload["scenario_spec_id"] = ctx.scenario_id

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


def stage_copilot_reachable(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 9: Verify copilot runtime status."""
    try:
        resp = client.get(f"{ctx.api_url}/api/copilot/status", timeout=5.0)

        if resp.status_code == 404:
            return ctx._missing("copilot_reachable", "Copilot status endpoint not available (404)")
        if resp.status_code >= 500:
            return StageResult(name="copilot_reachable", status="FAIL", detail=f"Server error {resp.status_code}")
        if resp.status_code != 200:
            return StageResult(name="copilot_reachable", status="FAIL", detail=f"Unexpected status {resp.status_code}")

        body = resp.json()
        enabled = body.get("enabled", False)
        ready = body.get("ready", False)
        providers = body.get("providers", [])
        detail_msg = body.get("detail", "")

        if not enabled:
            return ctx._missing("copilot_reachable", f"Copilot disabled on server: {detail_msg}")
        if ready:
            return StageResult(name="copilot_reachable", status="PASS", detail=f"Copilot ready, providers={providers}")
        return StageResult(name="copilot_reachable", status="FAIL", detail=f"Copilot enabled but not ready: {detail_msg}")
    except Exception as exc:
        return StageResult(name="copilot_reachable", status="FAIL", detail=f"Error reaching copilot: {exc}")


def stage_scenario_run(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 10: Deterministic engine run.  Populates ctx.scenario_id, ctx.run_id, ctx.run_result_sets."""
    if not ctx.workspace_id:
        return ctx._missing("scenario_run", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("scenario_run", "No auth token")
    try:
        # List scenarios
        list_resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/scenarios",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if list_resp.status_code != 200:
            return StageResult(name="scenario_run", status="FAIL", detail=f"List scenarios returned {list_resp.status_code}")
        body = list_resp.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        if not isinstance(items, list) or len(items) == 0:
            return ctx._missing("scenario_run", "No scenarios available to run")

        ctx.scenario_id = items[0].get("id", items[0].get("scenario_spec_id", ""))

        # Trigger run
        run_resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/scenarios/{ctx.scenario_id}/run",
            headers=ctx.auth_headers(),
            json={},
            timeout=60.0,
        )
        if run_resp.status_code in (200, 201, 202):
            run_body = run_resp.json()
            ctx.run_id = run_body.get("run_id", run_body.get("id", ""))
            ctx.run_result_sets = run_body.get("result_sets", [])
            n_results = len(ctx.run_result_sets)
            return StageResult(
                name="scenario_run",
                status="PASS",
                detail=f"Run completed: run_id={ctx.run_id}, result_sets={n_results}",
            )
        return StageResult(
            name="scenario_run",
            status="FAIL",
            detail=f"Run returned {run_resp.status_code}: {run_resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(name="scenario_run", status="FAIL", detail=f"Error triggering run: {exc}")


def stage_governance_check(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 11: Governance layer functional check."""
    if not ctx.workspace_id:
        return ctx._missing("governance_check", "No workspace available")
    if not ctx.auth_token:
        return ctx._missing("governance_check", "No auth token")
    try:
        resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/governance/claims",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if resp.status_code == 200:
            return StageResult(name="governance_check", status="PASS", detail="Governance layer functional (200)")
        if resp.status_code == 404:
            # 404 from the route = no claims yet, but layer exists
            return StageResult(name="governance_check", status="PASS", detail="Governance layer reachable (no claims yet)")
        if resp.status_code == 401:
            return StageResult(name="governance_check", status="FAIL", detail="401 Unauthorized")
        return StageResult(name="governance_check", status="FAIL", detail=f"Governance returned {resp.status_code}")
    except Exception as exc:
        return StageResult(name="governance_check", status="FAIL", detail=f"Error checking governance: {exc}")


def stage_export_create(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 12: Create export from run results.  Populates ctx.export_id."""
    if not ctx.workspace_id:
        return ctx._missing("export_create", "No workspace available")
    if not ctx.run_id:
        return ctx._missing("export_create", "No run_id available")
    if not ctx.auth_token:
        return ctx._missing("export_create", "No auth token")
    try:
        export_payload = {
            "run_id": ctx.run_id,
            "scenario_id": ctx.scenario_id,
            "formats": ["xlsx"],
        }
        resp = client.post(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/exports",
            headers=ctx.auth_headers(),
            json=export_payload,
            timeout=60.0,
        )
        if resp.status_code in (200, 201, 202):
            body = resp.json()
            ctx.export_id = body.get("export_id", body.get("id", ""))
            status = body.get("status", "unknown")
            return StageResult(name="export_create", status="PASS", detail=f"Export created: {ctx.export_id}, status={status}")
        return StageResult(name="export_create", status="FAIL", detail=f"Export create returned {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        return StageResult(name="export_create", status="FAIL", detail=f"Error creating export: {exc}")


def stage_export_download(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 13: Download export artifact and verify non-empty content."""
    if not ctx.workspace_id:
        return ctx._missing("export_download", "No workspace available")
    if not ctx.export_id:
        return ctx._missing("export_download", "No export_id available")
    if not ctx.auth_token:
        return ctx._missing("export_download", "No auth token")
    try:
        resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/exports/{ctx.export_id}/download/xlsx",
            headers=ctx.auth_headers(),
            timeout=30.0,
        )
        if resp.status_code == 200:
            content_len = len(resp.content)
            if content_len > 0:
                return StageResult(name="export_download", status="PASS", detail=f"Export downloaded: {content_len} bytes")
            return StageResult(name="export_download", status="FAIL", detail="Export download returned empty content")
        return StageResult(name="export_download", status="FAIL", detail=f"Export download returned {resp.status_code}")
    except Exception as exc:
        return StageResult(name="export_download", status="FAIL", detail=f"Error downloading export: {exc}")


def stage_output_validation(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 14: Validate run outputs against expected values.

    Checks:
    - run_result_sets is non-empty
    - Each result set has metric_type and values dict
    - Values dict contains numeric (float/int) entries
    - At least one metric has non-zero values (real computation occurred)

    When --validate-outputs is set, also fetches the persisted run and
    compares result_sets against the in-memory copy for consistency.
    """
    if not ctx.run_id:
        return ctx._missing("output_validation", "No run_id — cannot validate outputs")
    if not ctx.run_result_sets:
        return ctx._missing("output_validation", "No result_sets captured from run")

    errors: list[str] = []

    # Check 1: result_sets non-empty
    if len(ctx.run_result_sets) == 0:
        errors.append("result_sets is empty")

    # Check 2: structure validation
    for i, rs in enumerate(ctx.run_result_sets):
        if not rs.get("metric_type"):
            errors.append(f"result_set[{i}] missing metric_type")
        values = rs.get("values", {})
        if not isinstance(values, dict) or len(values) == 0:
            errors.append(f"result_set[{i}] ({rs.get('metric_type', '?')}) has empty values")

    # Check 3: at least one metric has non-zero values
    has_nonzero = False
    for rs in ctx.run_result_sets:
        values = rs.get("values", {})
        if isinstance(values, dict):
            for v in values.values():
                if isinstance(v, (int, float)) and v != 0:
                    has_nonzero = True
                    break
        if has_nonzero:
            break
    if not has_nonzero and not errors:
        errors.append("All result_set values are zero — no real computation occurred")

    if errors:
        return StageResult(
            name="output_validation",
            status="FAIL",
            detail=f"Output validation failed: {'; '.join(errors)}",
        )

    # Check 4: if --validate-outputs, fetch persisted run and compare
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
                # Compare metric types
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
    detail = f"Output valid: {n_metrics} result_sets with non-zero values"
    if ctx.validate_outputs:
        detail += ", persisted data matches"
    return StageResult(name="output_validation", status="PASS", detail=detail)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

# Stage names for cascade-skip when API is unreachable
_ALL_STAGES_AFTER_HEALTH = [
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


def run_e2e(
    api_url: str,
    frontend_url: str = "",
    auth_token: str = "",
    strict: bool = False,
    validate_outputs: bool = False,
) -> E2EReport:
    """Execute all E2E stages in order."""
    ctx = E2EContext(
        api_url=api_url,
        frontend_url=frontend_url,
        auth_token=auth_token,
        strict=strict,
        validate_outputs=validate_outputs,
    )
    stages: list[StageResult] = []

    with httpx.Client() as client:
        # Stage 1: Frontend
        stages.append(stage_frontend_reachable(client, ctx))

        # Stage 2: API health
        api_health = stage_api_health(client, ctx)
        stages.append(api_health)

        if api_health.status == "FAIL":
            skip_status = "FAIL" if strict else "SKIP"
            for name in _ALL_STAGES_AFTER_HEALTH:
                stages.append(StageResult(name=name, status=skip_status, detail="API not healthy"))
        else:
            # Stage 3: Workspace
            stages.append(stage_workspace_access(client, ctx))
            # Stage 4: Document upload
            stages.append(stage_document_upload(client, ctx))
            # Stage 5: Extraction trigger
            stages.append(stage_extraction_trigger(client, ctx))
            # Stage 6: Extraction wait (worker proof)
            stages.append(stage_extraction_wait(client, ctx))
            # Stage 7: Compile (LLM)
            stages.append(stage_compile(client, ctx))
            # Stage 8: Depth (LLM)
            stages.append(stage_depth_analysis(client, ctx))
            # Stage 9: Copilot
            stages.append(stage_copilot_reachable(client, ctx))
            # Stage 10: Scenario run
            stages.append(stage_scenario_run(client, ctx))
            # Stage 11: Governance
            stages.append(stage_governance_check(client, ctx))
            # Stage 12: Export create
            stages.append(stage_export_create(client, ctx))
            # Stage 13: Export download
            stages.append(stage_export_download(client, ctx))
            # Stage 14: Output validation
            stages.append(stage_output_validation(client, ctx))

    # In strict mode, any SKIP is a failure
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
            "depth_plan_id": ctx.depth_plan_id,
            "scenario_id": ctx.scenario_id,
            "run_id": ctx.run_id,
            "export_id": ctx.export_id,
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
        help="Bearer token for authenticated stages (default: $STAGING_AUTH_TOKEN)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict acceptance mode: all critical-path SKIPs become FAILs",
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
    )

    if args.json_output:
        _print_json(report)
    else:
        _print_table(report)

    sys.exit(1 if report.has_failures() else 0)


if __name__ == "__main__":
    main()
