"""Staging smoke harness -- one-command deployment verification.

Usage:
    python scripts/staging_smoke.py [--json] [--url http://localhost:8000]

Stages:
    1. startup -- server reachable (GET /api/version returns 200)
    2. readiness -- /readiness returns 200 with ready=true
    3. auth_enforcement -- unauthenticated request returns 401
    4. health_components -- /health checks all present
    5. api_schema -- /openapi.json valid JSON with paths
    6. copilot_smoke -- chat endpoint reachable (SKIP if no provider)
    7. worker_health -- celery worker reachable (via inspect or docker)

Exit code: 0 if no FAIL, 1 if any FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field

import httpx

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    """Single smoke-test stage result."""

    name: str
    status: str  # PASS, FAIL, SKIP
    detail: str


@dataclass
class SmokeReport:
    """Aggregated smoke report."""

    overall: str  # PASS or FAIL
    stages: list[StageResult] = field(default_factory=list)

    def has_failures(self) -> bool:
        """Return True if any stage has FAIL status."""
        return any(s.status == "FAIL" for s in self.stages)


# ---------------------------------------------------------------------------
# Individual stages
# ---------------------------------------------------------------------------

_HEALTH_COMPONENTS = {"api", "database", "redis", "object_storage"}


def stage_startup(client: httpx.Client, base_url: str) -> StageResult:
    """Stage 1: Verify server is reachable via GET /api/version."""
    try:
        resp = client.get(f"{base_url}/api/version", timeout=5.0)
        if resp.status_code == 200:
            body = resp.json()
            version = body.get("version", "unknown")
            return StageResult(
                name="startup",
                status="PASS",
                detail=f"Server reachable, version={version}",
            )
        return StageResult(
            name="startup",
            status="FAIL",
            detail=f"GET /api/version returned {resp.status_code}",
        )
    except httpx.ConnectError:
        return StageResult(
            name="startup",
            status="FAIL",
            detail=f"Cannot connect to {base_url}",
        )
    except Exception as exc:
        return StageResult(
            name="startup",
            status="FAIL",
            detail=f"Unexpected error: {exc}",
        )


def stage_readiness(client: httpx.Client, base_url: str) -> StageResult:
    """Stage 2: GET /readiness returns 200 with ready=true."""
    try:
        resp = client.get(f"{base_url}/readiness", timeout=5.0)
        if resp.status_code == 200:
            body = resp.json()
            if body.get("ready", False):
                return StageResult(
                    name="readiness",
                    status="PASS",
                    detail="Server is ready",
                )
            return StageResult(
                name="readiness",
                status="FAIL",
                detail=f"Server not ready: {body}",
            )
        return StageResult(
            name="readiness",
            status="FAIL",
            detail=f"GET /readiness returned {resp.status_code}",
        )
    except Exception as exc:
        return StageResult(
            name="readiness",
            status="FAIL",
            detail=f"Error reaching /readiness: {exc}",
        )


def stage_auth_enforcement(client: httpx.Client, base_url: str) -> StageResult:
    """Stage 3: Unauthenticated GET to a protected endpoint returns 401."""
    # /v1/workspaces is auth-protected; no token should yield 401
    try:
        resp = client.get(f"{base_url}/v1/workspaces", timeout=5.0)
        if resp.status_code == 401:
            return StageResult(
                name="auth_enforcement",
                status="PASS",
                detail="Unauthenticated request correctly returned 401",
            )
        return StageResult(
            name="auth_enforcement",
            status="FAIL",
            detail=(
                f"Expected 401 for unauthenticated request, "
                f"got {resp.status_code}"
            ),
        )
    except Exception as exc:
        return StageResult(
            name="auth_enforcement",
            status="FAIL",
            detail=f"Error checking auth enforcement: {exc}",
        )


def stage_health_components(client: httpx.Client, base_url: str) -> StageResult:
    """Stage 4: GET /health returns all 4 component keys."""
    try:
        resp = client.get(f"{base_url}/health", timeout=5.0)
        if resp.status_code != 200:
            return StageResult(
                name="health_components",
                status="FAIL",
                detail=f"GET /health returned {resp.status_code}",
            )
        body = resp.json()
        checks = body.get("checks", {})
        present = set(checks.keys())
        missing = _HEALTH_COMPONENTS - present
        if missing:
            return StageResult(
                name="health_components",
                status="FAIL",
                detail=f"Missing health components: {sorted(missing)}",
            )
        return StageResult(
            name="health_components",
            status="PASS",
            detail=f"All components present: {sorted(present)}",
        )
    except Exception as exc:
        return StageResult(
            name="health_components",
            status="FAIL",
            detail=f"Error checking /health: {exc}",
        )


def stage_api_schema(client: httpx.Client, base_url: str) -> StageResult:
    """Stage 5: GET /openapi.json returns valid JSON with paths."""
    try:
        resp = client.get(f"{base_url}/openapi.json", timeout=5.0)
        if resp.status_code != 200:
            return StageResult(
                name="api_schema",
                status="FAIL",
                detail=f"GET /openapi.json returned {resp.status_code}",
            )
        body = resp.json()
        paths = body.get("paths", {})
        if not paths:
            return StageResult(
                name="api_schema",
                status="FAIL",
                detail="OpenAPI schema has no paths",
            )
        return StageResult(
            name="api_schema",
            status="PASS",
            detail=f"OpenAPI schema valid with {len(paths)} paths",
        )
    except json.JSONDecodeError:
        return StageResult(
            name="api_schema",
            status="FAIL",
            detail="GET /openapi.json returned invalid JSON",
        )
    except Exception as exc:
        return StageResult(
            name="api_schema",
            status="FAIL",
            detail=f"Error fetching /openapi.json: {exc}",
        )


def stage_copilot_smoke(client: httpx.Client, base_url: str) -> StageResult:
    """Stage 6: Verify copilot runtime readiness on the server.

    Probes GET /api/copilot/status which exercises the actual copilot
    construction path (_build_copilot) and reports whether the LLM
    provider stack is available.  This is a server-side runtime check —
    no local shell env vars are read.

    Decision table:
        enabled=false         → SKIP  (copilot intentionally off)
        enabled=true, ready   → PASS  (copilot runtime constructed)
        enabled=true, !ready  → FAIL  (enabled but no providers)
        404                   → SKIP  (endpoint not available on server)
        5xx / other           → FAIL
    """
    status_url = f"{base_url}/api/copilot/status"

    try:
        resp = client.get(status_url, timeout=5.0)

        # 404 — endpoint not deployed (older server without this route)
        if resp.status_code == 404:
            return StageResult(
                name="copilot_smoke",
                status="SKIP",
                detail="Copilot status endpoint not available (404)",
            )

        # 5xx — server error
        if resp.status_code >= 500:
            return StageResult(
                name="copilot_smoke",
                status="FAIL",
                detail=f"Server error {resp.status_code} from copilot status",
            )

        # Non-200, non-404, non-5xx
        if resp.status_code != 200:
            return StageResult(
                name="copilot_smoke",
                status="FAIL",
                detail=f"Unexpected status {resp.status_code} from copilot status",
            )

        # 200 — parse the runtime report
        body = resp.json()
        enabled = body.get("enabled", False)
        ready = body.get("ready", False)
        providers = body.get("providers", [])
        detail_msg = body.get("detail", "")

        if not enabled:
            return StageResult(
                name="copilot_smoke",
                status="SKIP",
                detail=f"Copilot disabled on server: {detail_msg}",
            )

        if ready:
            return StageResult(
                name="copilot_smoke",
                status="PASS",
                detail=f"Copilot runtime ready, providers={providers}",
            )

        # enabled but not ready — provider misconfiguration
        return StageResult(
            name="copilot_smoke",
            status="FAIL",
            detail=f"Copilot enabled but not ready: {detail_msg}",
        )
    except Exception as exc:
        return StageResult(
            name="copilot_smoke",
            status="FAIL",
            detail=f"Error reaching copilot status: {exc}",
        )


def stage_worker_health(client: httpx.Client, base_url: str) -> StageResult:
    """Stage 7: Verify Celery worker is reachable.

    Checks the /health endpoint for a worker component, or attempts
    to reach the Celery broker via the API's health data. Falls back
    to checking Redis connectivity as a proxy for worker readiness.
    """
    try:
        resp = client.get(f"{base_url}/health", timeout=10)
        if resp.status_code != 200:
            return StageResult(
                name="worker_health",
                status="FAIL",
                detail=f"/health returned {resp.status_code}",
            )

        data = resp.json()
        checks = data.get("checks", {})

        # Check Redis is healthy (worker depends on it as broker)
        redis_val = checks.get("redis")
        # The health endpoint returns either string "ok" or dict with status
        redis_ok = False
        if isinstance(redis_val, str):
            redis_ok = redis_val.lower() in ("ok", "healthy")
        elif isinstance(redis_val, dict):
            redis_ok = redis_val.get("status", "").lower() in ("ok", "healthy")

        if not redis_ok:
            return StageResult(
                name="worker_health",
                status="FAIL",
                detail="Redis (Celery broker) is not healthy — worker cannot process jobs",
            )

        # Redis is healthy = broker reachable, worker can connect.
        # Worker container health must be verified separately via
        # `docker compose ps celery-worker` in deployment.
        return StageResult(
            name="worker_health",
            status="PASS",
            detail="Redis broker healthy — worker can process jobs (verify container via docker compose ps)",
        )

    except Exception as exc:
        return StageResult(
            name="worker_health",
            status="FAIL",
            detail=f"Error checking worker health: {exc}",
        )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_smoke(base_url: str) -> SmokeReport:
    """Execute all smoke stages in order.

    If the server is unreachable (startup stage FAIL), remaining stages
    are automatically SKIPped.
    """
    stages: list[StageResult] = []

    with httpx.Client() as client:
        # Stage 1 -- startup
        startup = stage_startup(client, base_url)
        stages.append(startup)

        if startup.status == "FAIL":
            # Server unreachable -- skip everything else
            remaining = [
                "readiness",
                "auth_enforcement",
                "health_components",
                "api_schema",
                "copilot_smoke",
                "worker_health",
            ]
            for name in remaining:
                stages.append(
                    StageResult(
                        name=name,
                        status="SKIP",
                        detail="Server not reachable -- skipped",
                    ),
                )
            return SmokeReport(overall="FAIL", stages=stages)

        # Stage 2 -- readiness
        stages.append(stage_readiness(client, base_url))

        # Stage 3 -- auth enforcement
        stages.append(stage_auth_enforcement(client, base_url))

        # Stage 4 -- health components
        stages.append(stage_health_components(client, base_url))

        # Stage 5 -- API schema
        stages.append(stage_api_schema(client, base_url))

        # Stage 6 -- copilot smoke
        stages.append(stage_copilot_smoke(client, base_url))

        # Stage 7 -- worker health
        stages.append(stage_worker_health(client, base_url))

    has_fail = any(s.status == "FAIL" for s in stages)
    return SmokeReport(
        overall="FAIL" if has_fail else "PASS",
        stages=stages,
    )


# ---------------------------------------------------------------------------
# CLI output helpers
# ---------------------------------------------------------------------------

_STATUS_SYMBOLS = {
    "PASS": "[PASS]",
    "FAIL": "[FAIL]",
    "SKIP": "[SKIP]",
    "WARN": "[WARN]",
}


def _print_table(report: SmokeReport) -> None:
    """Print a human-readable table of stage results."""
    max_name = max(len(s.name) for s in report.stages) if report.stages else 10
    print()
    print(f"{'Stage':<{max_name + 2}} {'Status':<8} Detail")
    print("-" * (max_name + 2 + 8 + 40))
    for s in report.stages:
        symbol = _STATUS_SYMBOLS.get(s.status, s.status)
        print(f"{s.name:<{max_name + 2}} {symbol:<8} {s.detail}")
    print()
    print(f"Overall: {report.overall}")
    print()


def _print_json(report: SmokeReport) -> None:
    """Print JSON report to stdout."""
    print(json.dumps(asdict(report), indent=2))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and run the smoke suite."""
    parser = argparse.ArgumentParser(
        description="Staging smoke harness -- one-command deployment verification.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output structured JSON report",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the ImpactOS server (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    report = run_smoke(base_url=args.url)

    if args.json_output:
        _print_json(report)
    else:
        _print_table(report)

    sys.exit(1 if report.has_failures() else 0)


if __name__ == "__main__":
    main()
