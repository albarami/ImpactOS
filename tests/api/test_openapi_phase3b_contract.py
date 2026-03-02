"""Phase 3B OpenAPI contract drift guard.

Asserts that all required Phase 3B backend endpoints (B-1..B-17) are
present in app.openapi() with the correct HTTP method and path.

Canonical ticket definitions from sprint prompt files:
  Sprint 1: B-1 Workspace, B-6 Taxonomy, B-13 Auth,
            B-14 Model versions, B-15 Coefficients
  Sprint 2: B-2 Doc list, B-3 Doc detail,
            B-9 Scenario list, B-10 Scenario get
  Sprint 3: B-4 Decision CRUD, B-5 Bulk approve,
            B-8 Audit trail, B-17 Compilation detail
  Sprint 4: B-11 Claims, B-7 Evidence
  Sprint 5: B-12 Export download, B-16 Run-from-scenario
"""

import pytest

from src.api.main import app

SPEC = app.openapi()
PATHS = SPEC.get("paths", {})


def _has(method: str, path: str) -> bool:
    return path in PATHS and method in PATHS[path]


# ---- Sprint 1 ----

# B-1: Workspace CRUD
B1_ROUTES = [
    ("post", "/v1/workspaces"),
    ("get", "/v1/workspaces"),
    ("get", "/v1/workspaces/{workspace_id}"),
    ("put", "/v1/workspaces/{workspace_id}"),
]

# B-6: Taxonomy browsing
B6_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/taxonomy/sectors"),
    ("get", "/v1/workspaces/{workspace_id}/taxonomy/sectors/search"),
    ("get", "/v1/workspaces/{workspace_id}/taxonomy/sectors/{sector_code}"),
]

# B-13: Auth contract (dev stub)
B13_ROUTES = [
    ("post", "/v1/auth/login"),
    ("post", "/v1/auth/logout"),
    ("get", "/v1/auth/me"),
]

# B-14: Model version list/detail
B14_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/models/versions"),
    ("get", "/v1/workspaces/{workspace_id}/models/versions/{model_version_id}"),
]

# B-15: Coefficient retrieval
B15_ROUTES = [
    (
        "get",
        "/v1/workspaces/{workspace_id}/models/versions/{model_version_id}/coefficients",
    ),
]

# ---- Sprint 2 ----

# B-2: Document list
B2_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/documents"),
]

# B-3: Document detail
B3_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/documents/{doc_id}"),
]

# B-9: Scenario list
B9_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/scenarios"),
]

# B-10: Scenario detail
B10_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}"),
]

# ---- Sprint 3 ----

# B-4: Per-line mapping decision state CRUD
B4_ROUTES = [
    (
        "get",
        "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}",
    ),
    (
        "put",
        "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}",
    ),
    (
        "post",
        "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions",
    ),
]

# B-5: Bulk threshold approval
B5_ROUTES = [
    (
        "post",
        "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/bulk-approve",
    ),
]

# B-8: Mapping audit trail
B8_ROUTES = [
    (
        "get",
        "/v1/workspaces/{workspace_id}/compiler/{compilation_id}/decisions/{line_item_id}/audit",
    ),
]

# B-17: GET compilation detail
B17_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/compiler/{compilation_id}"),
]

# ---- Sprint 4 ----

# B-11: Claim list/detail/update
B11_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/governance/claims"),
    ("get", "/v1/workspaces/{workspace_id}/governance/claims/{claim_id}"),
    ("put", "/v1/workspaces/{workspace_id}/governance/claims/{claim_id}"),
]

# B-7: Evidence list/detail/link + extraction wiring
B7_ROUTES = [
    ("get", "/v1/workspaces/{workspace_id}/governance/evidence"),
    ("get", "/v1/workspaces/{workspace_id}/governance/evidence/{snippet_id}"),
    (
        "post",
        "/v1/workspaces/{workspace_id}/governance/claims/{claim_id}/evidence",
    ),
]

# ---- Sprint 5 ----

# B-12: Export artifact persistence + download
B12_ROUTES = [
    (
        "get",
        "/v1/workspaces/{workspace_id}/exports/{export_id}/download/{format}",
    ),
]

# B-16: Run-from-scenario convenience
B16_ROUTES = [
    ("post", "/v1/workspaces/{workspace_id}/scenarios/{scenario_id}/run"),
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
                ALL_B_TICKETS.items(),
                key=lambda x: int(x[0].split("-")[1]),
            )
            for method, path in routes
        ],
        ids=lambda val: (
            val if isinstance(val, str) and val.startswith(("/", "B-")) else ""
        ),
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
