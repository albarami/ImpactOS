"""Phase 3B OpenAPI contract drift guard.

Asserts that all required Phase 3B backend endpoints (B-1..B-17) are
present in app.openapi() with the correct HTTP method and path.

This test fails if a required route is removed or renamed, catching
contract drift before it reaches frontend consumers.
"""

import pytest

from src.api.main import app

SPEC = app.openapi()
PATHS = SPEC.get("paths", {})


def _has(method: str, path: str) -> bool:
    return path in PATHS and method in PATHS[path]


# B-1: Workspace CRUD (Sprint 1)
B1_ROUTES = [
    ("post", "/v1/workspaces"),
    ("get", "/v1/workspaces"),
    ("get", "/v1/workspaces/{workspace_id}"),
    ("put", "/v1/workspaces/{workspace_id}"),
]

# B-2: Document upload + extraction trigger (Sprint 1)
B2_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/documents"),
    ("get", "/v1/workspaces/{workspace_id}/documents"),
    ("get", "/v1/workspaces/{workspace_id}/documents/{doc_id}"),
    ("post", "/v1/workspaces/{workspace_id}/documents/{doc_id}/extract"),
    ("get", "/v1/workspaces/{workspace_id}/jobs/{job_id}"),
]

# B-3: Line items read (Sprint 2)
B3_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/documents/{doc_id}/line-items"),
]

# B-4: Compiler compile + HITL decisions (Sprint 3)
B4_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/compiler/compile"),
    ("get", "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/status"),
    ("post", "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions"),
    ("get", "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}"),
    ("put", "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}"),
    (
        "get",
        "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}/audit",
    ),
    ("post", "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/bulk-approve"),
]

# B-5: Scenario CRUD + compile + lock (Sprint 1 / Sprint 5)
B5_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/scenarios"),
    ("post", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/compile"),
    ("post", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/mapping-decisions"),
    ("get", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/versions"),
    ("post", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/lock"),
]

# B-6: Engine runs + batch (Sprint 1)
B6_ROUTES = [
    ("post", "/v1/engine/models"),
    ("post", "/v1/workspaces/{workspace_id}/engine/runs"),
    ("get", "/v1/workspaces/{workspace_id}/engine/runs/{run_id}"),
    ("post", "/v1/workspaces/{workspace_id}/engine/batch"),
    ("get", "/v1/workspaces/{workspace_id}/engine/batch/{batch_id}"),
]

# B-7: Governance claims + NFF (Sprint 4)
B7_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/governance/claims/extract"),
    ("get", "/v1/workspaces/{workspace_id}/governance/claims"),
    ("get", "/v1/workspaces/{workspace_id}/governance/claims/{claim_id}"),
    ("put", "/v1/workspaces/{workspace_id}/governance/claims/{claim_id}"),
    ("post", "/v1/workspaces/{workspace_id}/governance/claims/{claim_id}/evidence"),
    ("post", "/v1/workspaces/{workspace_id}/governance/nff/check"),
    ("post", "/v1/workspaces/{workspace_id}/governance/assumptions"),
    ("post", "/v1/workspaces/{workspace_id}/governance/assumptions/{assumption_id}/approve"),
    ("get", "/v1/workspaces/{workspace_id}/governance/status/{run_id}"),
    ("get", "/v1/workspaces/{workspace_id}/governance/blocking-reasons/{run_id}"),
]

# B-8: Taxonomy sectors (Sprint 1)
B8_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/taxonomy/sectors"),
    ("get", "/v1/workspaces/{workspace_id}/taxonomy/sectors/{sector_code}"),
    ("get", "/v1/workspaces/{workspace_id}/taxonomy/sectors/search"),
]

# B-9: Scenario list (Sprint 2)
B9_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/scenarios"),
]

# B-10: Scenario detail (Sprint 2)
B10_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}"),
]

# B-11: Evidence + blocking reasons (Sprint 4)
B11_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/governance/evidence"),
    ("get", "/v1/workspaces/{workspace_id}/governance/evidence/{snippet_id}"),
]

# B-12: Export download (Sprint 5)
B12_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/exports"),
    ("get", "/v1/workspaces/{workspace_id}/exports/{export_id}"),
    ("get", "/v1/workspaces/{workspace_id}/exports/{export_id}/download/{format}"),
]

# B-13: Auth login/logout/me (Sprint 1)
B13_ROUTES = [
    ("post", "/v1/auth/login"),
    ("post", "/v1/auth/logout"),
    ("get", "/v1/auth/me"),
]

# B-14: Model version list + detail (workspace-scoped)
B14_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/models/versions"),
    ("get", "/v1/workspaces/{workspace_id}/models/versions/{model_version_id}"),
]

# B-15: Data quality
B15_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/runs/{run_id}/quality"),
    ("get", "/v1/workspaces/{workspace_id}/runs/{run_id}/quality"),
]

# B-16: Run-from-scenario (Sprint 5)
B16_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/run"),
]

# B-17: Full compilation get (Sprint 3)
B17_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/compiler/{compilation_id}"),
]

ALL_B_TICKETS = {
    "B-1": B1_ROUTES,
    "B-2": B2_ROUTES,
    "B-3": B3_ROUTES,
    "B-4": B4_ROUTES,
    "B-5": B5_ROUTES,
    "B-6": B6_ROUTES,
    "B-7": B7_ROUTES,
    "B-8": B8_ROUTES,
    "B-9": B9_ROUTES,
    "B-10": B10_ROUTES,
    "B-11": B11_ROUTES,
    "B-12": B12_ROUTES,
    "B-13": B13_ROUTES,
    "B-14": B14_ROUTES,
    "B-15": B15_ROUTES,
    "B-16": B16_ROUTES,
    "B-17": B17_ROUTES,
}


class TestPhase3BContractGuard:
    """Fail if any required Phase 3B endpoint is missing from OpenAPI."""

    @pytest.mark.parametrize(
        "ticket,method,path",
        [
            (ticket, method, path)
            for ticket, routes in sorted(
                ALL_B_TICKETS.items(), key=lambda x: int(x[0].split("-")[1]),
            )
            for method, path in routes
        ],
        ids=lambda val: val if isinstance(val, str) and val.startswith(("/", "B-")) else "",
    )
    def test_route_exists(self, ticket: str, method: str, path: str):
        assert _has(method, path), (
            f"{ticket}: {method.upper()} {path} missing from OpenAPI spec"
        )

    def test_openapi_path_count_minimum(self):
        assert len(PATHS) >= 88, (
            f"Expected >= 88 paths, got {len(PATHS)}"
        )

    def test_openapi_operation_count_minimum(self):
        ops = sum(
            len([m for m in v if m in {"get", "post", "put", "patch", "delete"}])
            for v in PATHS.values()
        )
        assert ops >= 106, f"Expected >= 106 operations, got {ops}"
