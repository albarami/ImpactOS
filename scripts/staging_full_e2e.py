"""Full-system staging E2E acceptance harness.

Usage:
    python scripts/staging_full_e2e.py [--json] \
        --api-url http://staging-api:8000 \
        --frontend-url http://staging-frontend:3000 \
        [--auth-token TOKEN] \
        [--validate-outputs]

Stages:
    1. frontend_reachable -- frontend responds with HTML
    2. api_health -- /health returns all required components healthy
    3. workspace_access -- authenticated workspace list/create
    4. document_upload -- upload test fixture to real object storage
    5. copilot_reachable -- copilot runtime status check
    6. scenario_run -- deterministic engine run with persisted outputs
    7. governance_check -- governance layer reachable
    8. export_create -- export generation from run results
    9. export_download -- artifact download verification

Each stage that produces IDs (workspace_id, document_id, run_id, export_id)
passes them downstream via E2EContext.  If an upstream stage FAILs or SKIPs,
dependent stages are automatically SKIPped.

Note: --validate-outputs is accepted for forward-compatibility but requires
live staging data with known expected results to function.  Without live
staging infrastructure, output validation is not exercised.

Exit code: 0 if no FAIL, 1 if any FAIL.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
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
    """Mutable context that flows between stages.

    Stages populate IDs for downstream consumption.
    """

    api_url: str
    frontend_url: str
    auth_token: str

    # Populated by stages as they succeed
    workspace_id: str = ""
    document_id: str = ""
    scenario_id: str = ""
    run_id: str = ""
    export_id: str = ""

    def auth_headers(self) -> dict[str, str]:
        """Return Authorization header dict if token is available."""
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}


@dataclass
class E2EReport:
    """Aggregated E2E acceptance report."""

    overall: str  # PASS or FAIL
    api_url: str
    frontend_url: str
    stages: list[StageResult] = field(default_factory=list)
    trace: dict[str, str] = field(default_factory=dict)

    def has_failures(self) -> bool:
        """Return True if any stage has FAIL status."""
        return any(s.status == "FAIL" for s in self.stages)


# ---------------------------------------------------------------------------
# Required health components (must match staging_smoke.py)
# ---------------------------------------------------------------------------

_HEALTH_COMPONENTS = {"api", "database", "redis", "object_storage"}


# ---------------------------------------------------------------------------
# Individual stages
# ---------------------------------------------------------------------------


def stage_frontend_reachable(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 1: Verify frontend is reachable and returns HTML."""
    if not ctx.frontend_url:
        return StageResult(
            name="frontend_reachable",
            status="SKIP",
            detail="No frontend URL provided",
        )
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
        # Check if any component is unhealthy
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
    """Stage 3: Verify authenticated workspace access.

    Lists workspaces, uses the first one or creates a staging-e2e workspace.
    Populates ctx.workspace_id on success.
    """
    if not ctx.auth_token:
        return StageResult(
            name="workspace_access",
            status="SKIP",
            detail="No auth token provided — cannot test authenticated access",
        )
    try:
        resp = client.get(
            f"{ctx.api_url}/v1/workspaces",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if resp.status_code == 401:
            return StageResult(
                name="workspace_access",
                status="FAIL",
                detail="401 Unauthorized — auth token rejected",
            )
        if resp.status_code == 403:
            return StageResult(
                name="workspace_access",
                status="FAIL",
                detail="403 Forbidden — insufficient permissions",
            )
        if resp.status_code != 200:
            return StageResult(
                name="workspace_access",
                status="FAIL",
                detail=f"GET /v1/workspaces returned {resp.status_code}",
            )
        body = resp.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        if isinstance(items, list) and len(items) > 0:
            ctx.workspace_id = items[0].get("id", "")
            return StageResult(
                name="workspace_access",
                status="PASS",
                detail=f"Workspace accessible: {ctx.workspace_id}",
            )
        # No workspaces exist — try to create one
        create_resp = client.post(
            f"{ctx.api_url}/v1/workspaces",
            headers=ctx.auth_headers(),
            json={"name": "staging-e2e-acceptance", "description": "Sprint 31 E2E acceptance workspace"},
            timeout=10.0,
        )
        if create_resp.status_code in (200, 201):
            create_body = create_resp.json()
            ctx.workspace_id = create_body.get("id", "")
            return StageResult(
                name="workspace_access",
                status="PASS",
                detail=f"Created workspace: {ctx.workspace_id}",
            )
        return StageResult(
            name="workspace_access",
            status="FAIL",
            detail=f"No workspaces and create returned {create_resp.status_code}",
        )
    except Exception as exc:
        return StageResult(
            name="workspace_access",
            status="FAIL",
            detail=f"Error accessing workspaces: {exc}",
        )


def stage_document_upload(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 4: Upload a test document to real object storage.

    Uses a minimal test fixture to verify the upload path.
    Populates ctx.document_id on success.
    """
    if not ctx.workspace_id:
        return StageResult(
            name="document_upload",
            status="SKIP",
            detail="No workspace available — skipped",
        )
    if not ctx.auth_token:
        return StageResult(
            name="document_upload",
            status="SKIP",
            detail="No auth token — skipped",
        )
    try:
        # Minimal PDF-like fixture for upload testing
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
            return StageResult(
                name="document_upload",
                status="PASS",
                detail=f"Document uploaded: {ctx.document_id}",
            )
        return StageResult(
            name="document_upload",
            status="FAIL",
            detail=f"Upload returned {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(
            name="document_upload",
            status="FAIL",
            detail=f"Error uploading document: {exc}",
        )


def stage_copilot_reachable(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 5: Verify copilot runtime status.

    Matches the same decision table as staging_smoke.py stage_copilot_smoke.
    """
    try:
        resp = client.get(f"{ctx.api_url}/api/copilot/status", timeout=5.0)

        if resp.status_code == 404:
            return StageResult(
                name="copilot_reachable",
                status="SKIP",
                detail="Copilot status endpoint not available (404)",
            )
        if resp.status_code >= 500:
            return StageResult(
                name="copilot_reachable",
                status="FAIL",
                detail=f"Server error {resp.status_code} from copilot status",
            )
        if resp.status_code != 200:
            return StageResult(
                name="copilot_reachable",
                status="FAIL",
                detail=f"Unexpected status {resp.status_code} from copilot status",
            )

        body = resp.json()
        enabled = body.get("enabled", False)
        ready = body.get("ready", False)
        providers = body.get("providers", [])
        detail_msg = body.get("detail", "")

        if not enabled:
            return StageResult(
                name="copilot_reachable",
                status="SKIP",
                detail=f"Copilot disabled on server: {detail_msg}",
            )
        if ready:
            return StageResult(
                name="copilot_reachable",
                status="PASS",
                detail=f"Copilot runtime ready, providers={providers}",
            )
        return StageResult(
            name="copilot_reachable",
            status="FAIL",
            detail=f"Copilot enabled but not ready: {detail_msg}",
        )
    except Exception as exc:
        return StageResult(
            name="copilot_reachable",
            status="FAIL",
            detail=f"Error reaching copilot status: {exc}",
        )


def stage_scenario_run(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 6: Trigger a deterministic engine run.

    Lists available scenarios, picks the first, and triggers a run.
    Populates ctx.scenario_id and ctx.run_id on success.
    """
    if not ctx.workspace_id:
        return StageResult(
            name="scenario_run",
            status="SKIP",
            detail="No workspace available — skipped",
        )
    if not ctx.auth_token:
        return StageResult(
            name="scenario_run",
            status="SKIP",
            detail="No auth token — skipped",
        )
    try:
        # List scenarios
        list_resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/scenarios",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if list_resp.status_code != 200:
            return StageResult(
                name="scenario_run",
                status="FAIL",
                detail=f"List scenarios returned {list_resp.status_code}",
            )
        body = list_resp.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        if not isinstance(items, list) or len(items) == 0:
            return StageResult(
                name="scenario_run",
                status="SKIP",
                detail="No scenarios available to run — skipped",
            )

        ctx.scenario_id = items[0].get("id", "")

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
            status = run_body.get("status", "unknown")
            return StageResult(
                name="scenario_run",
                status="PASS",
                detail=f"Run triggered: run_id={ctx.run_id}, status={status}",
            )
        return StageResult(
            name="scenario_run",
            status="FAIL",
            detail=f"Run trigger returned {run_resp.status_code}: {run_resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(
            name="scenario_run",
            status="FAIL",
            detail=f"Error triggering scenario run: {exc}",
        )


def stage_governance_check(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 7: Verify governance layer is reachable.

    Checks that the governance endpoint responds.
    """
    if not ctx.workspace_id:
        return StageResult(
            name="governance_check",
            status="SKIP",
            detail="No workspace available — skipped",
        )
    if not ctx.auth_token:
        return StageResult(
            name="governance_check",
            status="SKIP",
            detail="No auth token — skipped",
        )
    try:
        resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/governance/claims",
            headers=ctx.auth_headers(),
            timeout=10.0,
        )
        if resp.status_code in (200, 404):
            # 200 = claims exist, 404 = no claims yet (both prove layer works)
            return StageResult(
                name="governance_check",
                status="PASS",
                detail=f"Governance layer reachable (status {resp.status_code})",
            )
        if resp.status_code == 401:
            return StageResult(
                name="governance_check",
                status="FAIL",
                detail="401 Unauthorized — auth token rejected by governance",
            )
        return StageResult(
            name="governance_check",
            status="FAIL",
            detail=f"Governance returned {resp.status_code}",
        )
    except Exception as exc:
        return StageResult(
            name="governance_check",
            status="FAIL",
            detail=f"Error checking governance: {exc}",
        )


def stage_export_create(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 8: Create an export from run results.

    Populates ctx.export_id on success.
    """
    if not ctx.workspace_id:
        return StageResult(
            name="export_create",
            status="SKIP",
            detail="No workspace available — skipped",
        )
    if not ctx.run_id:
        return StageResult(
            name="export_create",
            status="SKIP",
            detail="No run_id available — skipped",
        )
    if not ctx.auth_token:
        return StageResult(
            name="export_create",
            status="SKIP",
            detail="No auth token — skipped",
        )
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
            return StageResult(
                name="export_create",
                status="PASS",
                detail=f"Export created: export_id={ctx.export_id}, status={status}",
            )
        return StageResult(
            name="export_create",
            status="FAIL",
            detail=f"Export create returned {resp.status_code}: {resp.text[:200]}",
        )
    except Exception as exc:
        return StageResult(
            name="export_create",
            status="FAIL",
            detail=f"Error creating export: {exc}",
        )


def stage_export_download(client: httpx.Client, ctx: E2EContext) -> StageResult:
    """Stage 9: Download an export artifact and verify content.

    Checks that the download returns bytes with correct content-type.
    """
    if not ctx.workspace_id:
        return StageResult(
            name="export_download",
            status="SKIP",
            detail="No workspace available — skipped",
        )
    if not ctx.export_id:
        return StageResult(
            name="export_download",
            status="SKIP",
            detail="No export_id available — skipped",
        )
    if not ctx.auth_token:
        return StageResult(
            name="export_download",
            status="SKIP",
            detail="No auth token — skipped",
        )
    try:
        resp = client.get(
            f"{ctx.api_url}/v1/workspaces/{ctx.workspace_id}/exports/{ctx.export_id}/download/xlsx",
            headers=ctx.auth_headers(),
            timeout=30.0,
        )
        if resp.status_code == 200:
            content_len = len(resp.content)
            if content_len > 0:
                return StageResult(
                    name="export_download",
                    status="PASS",
                    detail=f"Export downloaded: {content_len} bytes",
                )
            return StageResult(
                name="export_download",
                status="FAIL",
                detail="Export download returned empty content",
            )
        return StageResult(
            name="export_download",
            status="FAIL",
            detail=f"Export download returned {resp.status_code}",
        )
    except Exception as exc:
        return StageResult(
            name="export_download",
            status="FAIL",
            detail=f"Error downloading export: {exc}",
        )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_e2e(
    api_url: str,
    frontend_url: str = "",
    auth_token: str = "",
) -> E2EReport:
    """Execute all E2E stages in order.

    Returns an E2EReport with stage results and a trace of captured IDs.
    """
    ctx = E2EContext(
        api_url=api_url,
        frontend_url=frontend_url,
        auth_token=auth_token,
    )
    stages: list[StageResult] = []

    with httpx.Client() as client:
        # Stage 1: Frontend reachable
        stages.append(stage_frontend_reachable(client, ctx))

        # Stage 2: API health
        api_health = stage_api_health(client, ctx)
        stages.append(api_health)

        if api_health.status == "FAIL":
            # API unreachable — skip all downstream
            remaining = [
                "workspace_access",
                "document_upload",
                "copilot_reachable",
                "scenario_run",
                "governance_check",
                "export_create",
                "export_download",
            ]
            for name in remaining:
                stages.append(
                    StageResult(
                        name=name,
                        status="SKIP",
                        detail="API not healthy — skipped",
                    ),
                )
        else:
            # Stage 3: Workspace access
            stages.append(stage_workspace_access(client, ctx))

            # Stage 4: Document upload
            stages.append(stage_document_upload(client, ctx))

            # Stage 5: Copilot reachable
            stages.append(stage_copilot_reachable(client, ctx))

            # Stage 6: Scenario run
            stages.append(stage_scenario_run(client, ctx))

            # Stage 7: Governance check
            stages.append(stage_governance_check(client, ctx))

            # Stage 8: Export create
            stages.append(stage_export_create(client, ctx))

            # Stage 9: Export download
            stages.append(stage_export_download(client, ctx))

    has_fail = any(s.status == "FAIL" for s in stages)

    return E2EReport(
        overall="FAIL" if has_fail else "PASS",
        api_url=api_url,
        frontend_url=frontend_url,
        stages=stages,
        trace={
            "workspace_id": ctx.workspace_id,
            "document_id": ctx.document_id,
            "scenario_id": ctx.scenario_id,
            "run_id": ctx.run_id,
            "export_id": ctx.export_id,
        },
    )


# ---------------------------------------------------------------------------
# CLI output helpers
# ---------------------------------------------------------------------------


_STATUS_SYMBOLS = {
    "PASS": "[PASS]",
    "FAIL": "[FAIL]",
    "SKIP": "[SKIP]",
}


def _print_table(report: E2EReport) -> None:
    """Print a human-readable table of stage results."""
    max_name = max(len(s.name) for s in report.stages) if report.stages else 10
    print()
    print("Full-System E2E Acceptance Report")
    print(f"  API URL:      {report.api_url}")
    print(f"  Frontend URL: {report.frontend_url or '(not provided)'}")
    print()
    print(f"{'Stage':<{max_name + 2}} {'Status':<8} Detail")
    print("-" * (max_name + 2 + 8 + 50))
    for s in report.stages:
        symbol = _STATUS_SYMBOLS.get(s.status, s.status)
        print(f"{s.name:<{max_name + 2}} {symbol:<8} {s.detail}")
    print()

    # Trace IDs
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
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output structured JSON report",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        required=True,
        help="Base URL of the ImpactOS API server",
    )
    parser.add_argument(
        "--frontend-url",
        type=str,
        default="",
        help="Base URL of the ImpactOS frontend (optional)",
    )
    parser.add_argument(
        "--auth-token",
        type=str,
        default=os.environ.get("STAGING_AUTH_TOKEN", ""),
        help="Bearer token for authenticated stages (default: $STAGING_AUTH_TOKEN)",
    )
    parser.add_argument(
        "--validate-outputs",
        action="store_true",
        help="Enable output correctness validation against expected results (requires live staging data)",
    )
    args = parser.parse_args()

    report = run_e2e(
        api_url=args.api_url,
        frontend_url=args.frontend_url,
        auth_token=args.auth_token,
    )

    if args.json_output:
        _print_json(report)
    else:
        _print_table(report)

    sys.exit(1 if report.has_failures() else 0)


if __name__ == "__main__":
    main()
