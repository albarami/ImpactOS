# Sprint 23: Advanced Variance Bridges Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver deterministic, artifact-linked variance bridge analytics with persistence, additive API, and boardroom-ready explainability frontend.

**Architecture:** Normalize migration test DSN first (S23-0), then build advanced bridge engine fetching real RunSnapshot/ResultSet/ScenarioSpec artifacts (S23-1), persist as workspace-scoped analytics with idempotent config_hash (S23-2), expose additive API + boardroom waterfall UX (S23-3), sync docs/evidence (S23-4).

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy async, Alembic, NumPy (engine), Next.js 15, React 18, TanStack Query, Vitest.

**Design doc:** `docs/plans/2026-03-05-sprint23-advanced-variance-bridges-design.md`

---

## Task 1: S23-0 — Create shared migration test helper

**Files:**
- Create: `tests/migration/pg_migration_helpers.py`
- Test: `tests/migration/test_012_runseries_postgres.py` (will verify import works)

**Step 1: Write the shared helper module**

Create `tests/migration/pg_migration_helpers.py`:

```python
"""Shared helper for Postgres migration tests (012-017).

Policy (Sprint 23 S23-0):
- Single DSN from env var MIGRATION_TEST_DSN.
- No hardcoded credentials in any test file.
- If MIGRATION_TEST_DSN is unset:
  - CI (CI=true): RuntimeError — must be set.
  - Local dev: skip with explicit reason.
- Uses asyncpg for introspection. Uses subprocess for alembic.
"""

import os
import subprocess
import sys

import pytest

# ---------------------------------------------------------------------------
# DSN policy
# ---------------------------------------------------------------------------

_CI = os.environ.get("CI", "").lower() in ("true", "1", "yes")
_SKIP_PG = os.environ.get("IMPACTOS_SKIP_PG_MIGRATION", "0") == "1"

MIGRATION_TEST_DSN: str | None = os.environ.get("MIGRATION_TEST_DSN")

if _CI and not MIGRATION_TEST_DSN and not _SKIP_PG:
    raise RuntimeError(
        "MIGRATION_TEST_DSN must be set in CI. "
        "Set IMPACTOS_SKIP_PG_MIGRATION=1 to explicitly skip."
    )


def _dsn_for_asyncpg() -> str:
    """Return DSN suitable for asyncpg (strip +asyncpg prefix if present)."""
    dsn = MIGRATION_TEST_DSN or ""
    return dsn.replace("postgresql+asyncpg://", "postgresql://")


def _dsn_for_alembic() -> str:
    """Return DSN suitable for Alembic DATABASE_URL (must use +asyncpg)."""
    dsn = MIGRATION_TEST_DSN or ""
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


def _pg_reachable() -> bool:
    """Quick check if Postgres is reachable at MIGRATION_TEST_DSN."""
    if not MIGRATION_TEST_DSN:
        return False
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import asyncio, asyncpg\n"
                "async def _probe():\n"
                f"    c = await asyncpg.connect('{_dsn_for_asyncpg()}', timeout=3)\n"
                "    await c.close()\n"
                "asyncio.run(_probe())\n",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


PG_AVAILABLE: bool = not _SKIP_PG and _pg_reachable()

_skip_reason = (
    "IMPACTOS_SKIP_PG_MIGRATION=1"
    if _SKIP_PG
    else "MIGRATION_TEST_DSN not set or Postgres not reachable"
)

pg_skip_marker = pytest.mark.skipif(not PG_AVAILABLE, reason=_skip_reason)


# ---------------------------------------------------------------------------
# Alembic helpers
# ---------------------------------------------------------------------------


def alembic_env() -> dict[str, str]:
    """Build env dict for alembic subprocesses with correct DATABASE_URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = _dsn_for_alembic()
    return env


def run_alembic(*args: str) -> subprocess.CompletedProcess:
    """Run alembic command as subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=alembic_env(),
    )


# ---------------------------------------------------------------------------
# DB introspection helpers
# ---------------------------------------------------------------------------

_ASYNCPG_DSN_LAZY: str = ""


def _get_dsn() -> str:
    global _ASYNCPG_DSN_LAZY
    if not _ASYNCPG_DSN_LAZY:
        _ASYNCPG_DSN_LAZY = _dsn_for_asyncpg()
    return _ASYNCPG_DSN_LAZY


def table_exists(table_name: str) -> bool:
    """Check if a table exists on Postgres via asyncpg subprocess."""
    script = (
        "import asyncio, asyncpg\n"
        "async def check():\n"
        f"    conn = await asyncpg.connect('{_get_dsn()}', timeout=3)\n"
        "    try:\n"
        f"        val = await conn.fetchval(\n"
        f'            "SELECT table_name FROM information_schema.tables "\n'
        f"            \"WHERE table_name = '{table_name}'\"\n"
        f"        )\n"
        "        print('EXISTS' if val else 'MISSING')\n"
        "    finally:\n"
        "        await conn.close()\n"
        "asyncio.run(check())\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return "EXISTS" in r.stdout


def get_columns(table_name: str) -> list[str]:
    """Return column names for a table via asyncpg subprocess."""
    script = (
        "import asyncio, asyncpg\n"
        "async def check():\n"
        f"    conn = await asyncpg.connect('{_get_dsn()}', timeout=3)\n"
        "    try:\n"
        f"        rows = await conn.fetch(\n"
        f'            "SELECT column_name FROM information_schema.columns "\n'
        f"            \"WHERE table_name = '{table_name}' ORDER BY ordinal_position\"\n"
        f"        )\n"
        "        print(','.join(r['column_name'] for r in rows))\n"
        "    finally:\n"
        "        await conn.close()\n"
        "asyncio.run(check())\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.stdout.strip():
        return r.stdout.strip().split(",")
    return []


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists on a table."""
    return column_name in get_columns(table_name)


def exec_sql(sql: str) -> str:
    """Execute arbitrary SQL via asyncpg subprocess, return stdout."""
    script = (
        "import asyncio, asyncpg\n"
        "async def run():\n"
        f"    conn = await asyncpg.connect('{_get_dsn()}', timeout=3)\n"
        "    try:\n"
        f"        await conn.execute({sql!r})\n"
        "        print('OK')\n"
        "    except Exception as e:\n"
        "        print(f'ERROR:{type(e).__name__}:{e}')\n"
        "    finally:\n"
        "        await conn.close()\n"
        "asyncio.run(run())\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return r.stdout.strip()
```

**Step 2: Verify helper imports correctly**

Run: `python -c "from tests.migration.pg_migration_helpers import PG_AVAILABLE, pg_skip_marker; print('OK', PG_AVAILABLE)"`

Expected: `OK True` (if DSN set) or `OK False` (if not set, no crash)

**Step 3: Commit**

```bash
git add tests/migration/pg_migration_helpers.py
git commit -m "[sprint23] add shared migration test helper with single DSN policy"
```

---

## Task 2: S23-0 — Refactor migration tests 012-017 to use shared helper

**Files:**
- Modify: `tests/migration/test_012_runseries_postgres.py`
- Modify: `tests/migration/test_013_sg_provenance_postgres.py`
- Modify: `tests/migration/test_014_assumption_workspace_postgres.py`
- Modify: `tests/migration/test_015_path_analyses_postgres.py`
- Modify: `tests/migration/test_016_portfolio_optimization_postgres.py`
- Modify: `tests/migration/test_017_workshop_sessions_postgres.py`

**Step 1: Refactor test_012**

Replace all DSN/helper boilerplate in `tests/migration/test_012_runseries_postgres.py`. The file currently uses `src.config.settings.get_settings()` for DSN. Replace with shared helper imports. Keep all test methods and test logic unchanged. Remove `_pg_reachable()`, `_run_alembic()`, inline asyncpg connection code. Use `from tests.migration.pg_migration_helpers import ...`.

The constraint tests (test_check_constraint_series_kind_enum, test_check_constraint_year_required, test_partial_unique_index_blocks_duplicate_annual) use in-process asyncpg with parsed DSN — refactor to use `exec_sql()` from helper, or keep asyncpg but get DSN from `MIGRATION_TEST_DSN` env var via the helper's `_dsn_for_asyncpg()`.

**Step 2: Refactor test_013**

Replace hardcoded `postgresql://impactos:impactos@localhost:5432/impactos` DSN. Import `pg_skip_marker, run_alembic` from helper. Remove per-file `_pg_reachable()` and `_run_alembic()`.

**Step 3: Refactor test_014**

Replace hardcoded `_PG_DSN` and `_ALEMBIC_DSN` lines. Import from helper. Remove `_pg_reachable()`, `_alembic_env()`, `_run_alembic()`, `_column_exists()`. Use `column_exists()` from helper.

**Step 4: Refactor test_015**

Replace hardcoded `postgres:Salim1977` DSN. Import from helper. Remove all 6 local helper functions (`_pg_reachable`, `_alembic_env`, `_run_alembic`, `_table_exists`, `_get_columns`, `_exec_sql`). Use shared equivalents.

**Step 5: Refactor test_016**

Same pattern as 015. Replace `postgres:Salim1977` DSN, remove 6 local helpers, import from shared.

**Step 6: Refactor test_017**

Same pattern as 015/016. Replace `postgres:Salim1977` DSN, remove 6 local helpers, import from shared.

**Step 7: Run migration test suite**

Run: `python -m pytest tests/migration/test_012_runseries_postgres.py tests/migration/test_013_sg_provenance_postgres.py tests/migration/test_014_assumption_workspace_postgres.py tests/migration/test_015_path_analyses_postgres.py tests/migration/test_016_portfolio_optimization_postgres.py tests/migration/test_017_workshop_sessions_postgres.py -q`

Expected: All tests pass (or skip uniformly if DSN not set). No per-file DSN drift.

**Step 8: Verify no hardcoded credentials remain**

Run: `Select-String -Path "tests\migration\test_01*.py" -Pattern "Salim1977|impactos:impactos|postgresql://postgres:" | Select-Object Filename, LineNumber, Line`

Expected: Zero matches.

**Step 9: Commit**

```bash
git add tests/migration/test_012_runseries_postgres.py tests/migration/test_013_sg_provenance_postgres.py tests/migration/test_014_assumption_workspace_postgres.py tests/migration/test_015_path_analyses_postgres.py tests/migration/test_016_portfolio_optimization_postgres.py tests/migration/test_017_workshop_sessions_postgres.py
git commit -m "[sprint23] normalize migration test dsn and ownership policy for 012-017"
```

---

## Task 3: S23-1 — Write failing tests for advanced variance bridge engine

**Files:**
- Modify: `tests/export/test_variance_bridge.py`

**Step 1: Write failing tests for the new engine**

Add new test classes to `tests/export/test_variance_bridge.py`. Keep existing `TestBasicBridge`, `TestDriverDecomposition`, `TestWaterfallDataset` for legacy backward compat (they test the old `VarianceBridge.compare(run_a=dict, run_b=dict)` interface).

Add new tests:

```python
"""Tests for advanced artifact-linked variance bridge (Sprint 23)."""

import hashlib
import json
from uuid import uuid4

import pytest

from src.export.variance_bridge import (
    AdvancedVarianceBridge,
    BridgeDiagnostics,
    BridgeReasonCode,
    BridgeResult,
    DriverType,
)


class TestAdvancedBridgeAttribution:
    """S23-1: Deterministic attribution from artifact diffs."""

    def test_phasing_driver_from_time_horizon_diff(self):
        """Phasing driver detected when time_horizon differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv1"),
            result_a=_result(total=100.0),
            result_b=_result(total=120.0),
            spec_a=_spec(time_horizon={"start": 2025, "end": 2030}),
            spec_b=_spec(time_horizon={"start": 2025, "end": 2035}),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.PHASING in driver_types

    def test_import_share_driver_from_shock_diff(self):
        """Import share driver detected when ImportSubstitution shocks differ."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=110.0),
            spec_a=_spec(shock_items=[{"type": "ImportSubstitution", "sector": "A", "value": 0.1}]),
            spec_b=_spec(shock_items=[{"type": "ImportSubstitution", "sector": "A", "value": 0.2}]),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.IMPORT_SHARE in driver_types

    def test_mapping_driver_from_version_diff(self):
        """Mapping driver detected when mapping_library_version_id differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(mapping_library_version_id="map_v1"),
            run_b_snapshot=_snap(mapping_library_version_id="map_v2"),
            result_a=_result(total=100.0),
            result_b=_result(total=115.0),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.MAPPING in driver_types

    def test_constraint_driver_from_version_diff(self):
        """Constraint driver detected when constraint_set_version_id differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(constraint_set_version_id="cs1"),
            run_b_snapshot=_snap(constraint_set_version_id="cs2"),
            result_a=_result(total=100.0),
            result_b=_result(total=108.0),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.CONSTRAINT in driver_types

    def test_model_version_driver_from_version_diff(self):
        """Model version driver detected when model_version_id differs."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=130.0),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.MODEL_VERSION in driver_types

    def test_feasibility_driver_from_constraint_shocks(self):
        """Feasibility driver detected when ConstraintOverride shocks differ."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=95.0),
            spec_a=_spec(shock_items=[]),
            spec_b=_spec(shock_items=[{"type": "ConstraintOverride", "sector": "X", "value": 0.5}]),
        )
        driver_types = [d.driver_type for d in result.drivers]
        assert DriverType.FEASIBILITY in driver_types


class TestAdvancedBridgeIdentity:
    """S23-1: Strict identity invariant."""

    def test_drivers_sum_to_total_variance(self):
        """sum(driver.impact) == total_variance within tolerance."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1", mapping_library_version_id="m1"),
            run_b_snapshot=_snap(model_version_id="mv2", mapping_library_version_id="m2"),
            result_a=_result(total=100.0),
            result_b=_result(total=150.0),
        )
        driver_sum = sum(d.impact for d in result.drivers)
        assert abs(driver_sum - result.total_variance) < 1e-9

    def test_zero_magnitudes_nonzero_variance_goes_to_residual(self):
        """All zero magnitudes + nonzero variance → 100% RESIDUAL."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),  # identical snapshots
            result_a=_result(total=100.0),
            result_b=_result(total=120.0),  # but different results
        )
        assert len(result.drivers) == 1
        assert result.drivers[0].driver_type == DriverType.RESIDUAL
        assert abs(result.drivers[0].impact - 20.0) < 1e-9

    def test_zero_variance_no_drivers(self):
        """Zero total variance → no drivers (or one RESIDUAL with 0)."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=100.0),
        )
        driver_sum = sum(d.impact for d in result.drivers)
        assert abs(driver_sum) < 1e-9

    def test_identity_tolerance_boundary(self):
        """Identity check uses 1e-9 tolerance."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=100.0 + 1e-10),
        )
        assert result.diagnostics.identity_verified


class TestAdvancedBridgeDeterminism:
    """S23-1: Deterministic replay."""

    def test_same_inputs_produce_identical_checksum(self):
        """Same inputs → identical output checksum."""
        kwargs = dict(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=130.0),
        )
        r1 = AdvancedVarianceBridge.compute_from_artifacts(**kwargs)
        r2 = AdvancedVarianceBridge.compute_from_artifacts(**kwargs)
        assert r1.diagnostics.checksum == r2.diagnostics.checksum

    def test_deterministic_driver_sort(self):
        """Drivers sorted by DriverType enum order, then abs(impact) desc."""
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(
                model_version_id="mv1",
                mapping_library_version_id="m1",
                constraint_set_version_id="cs1",
            ),
            run_b_snapshot=_snap(
                model_version_id="mv2",
                mapping_library_version_id="m2",
                constraint_set_version_id="cs2",
            ),
            result_a=_result(total=100.0),
            result_b=_result(total=160.0),
        )
        types = [d.driver_type for d in result.drivers]
        # Enum order: PHASING, IMPORT_SHARE, MAPPING, CONSTRAINT, MODEL_VERSION, FEASIBILITY, RESIDUAL
        type_indices = [list(DriverType).index(t) for t in types]
        assert type_indices == sorted(type_indices)


class TestAdvancedBridgeDiagnostics:
    """S23-1: Structured diagnostics payload."""

    def test_diagnostics_includes_checksum(self):
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=100.0),
        )
        assert result.diagnostics.checksum.startswith("sha256:")

    def test_diagnostics_identity_verified(self):
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(),
            run_b_snapshot=_snap(),
            result_a=_result(total=100.0),
            result_b=_result(total=120.0),
        )
        assert result.diagnostics.identity_verified is True

    def test_diagnostics_per_driver_metadata(self):
        result = AdvancedVarianceBridge.compute_from_artifacts(
            run_a_snapshot=_snap(model_version_id="mv1"),
            run_b_snapshot=_snap(model_version_id="mv2"),
            result_a=_result(total=100.0),
            result_b=_result(total=130.0),
        )
        mv_driver = next(d for d in result.drivers if d.driver_type == DriverType.MODEL_VERSION)
        assert mv_driver.raw_magnitude > 0
        assert mv_driver.weight > 0
        assert mv_driver.source_field is not None


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

def _snap(
    *,
    model_version_id: str = "mv_default",
    taxonomy_version_id: str = "tv_default",
    concordance_version_id: str = "cv_default",
    mapping_library_version_id: str = "ml_default",
    assumption_library_version_id: str = "al_default",
    prompt_pack_version_id: str = "pp_default",
    constraint_set_version_id: str | None = None,
) -> dict:
    """Build a minimal RunSnapshot-like dict for testing."""
    return {
        "model_version_id": model_version_id,
        "taxonomy_version_id": taxonomy_version_id,
        "concordance_version_id": concordance_version_id,
        "mapping_library_version_id": mapping_library_version_id,
        "assumption_library_version_id": assumption_library_version_id,
        "prompt_pack_version_id": prompt_pack_version_id,
        "constraint_set_version_id": constraint_set_version_id,
    }


def _result(*, total: float) -> dict:
    """Build a minimal ResultSet-like dict for testing."""
    return {"values": {"total": total}}


def _spec(
    *,
    time_horizon: dict | None = None,
    shock_items: list | None = None,
) -> dict:
    """Build a minimal ScenarioSpec-like dict for testing."""
    return {
        "time_horizon": time_horizon or {"start": 2025, "end": 2030},
        "shock_items": shock_items or [],
    }
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/export/test_variance_bridge.py::TestAdvancedBridgeAttribution -v`

Expected: FAIL — `ImportError: cannot import name 'AdvancedVarianceBridge'`

**Step 3: Commit failing tests**

```bash
git add tests/export/test_variance_bridge.py
git commit -m "[sprint23] add failing tests for advanced variance bridge attribution engine"
```

---

## Task 4: S23-1 — Implement advanced variance bridge engine

**Files:**
- Modify: `src/export/variance_bridge.py`
- Modify: `src/models/export.py`

**Step 1: Add bridge models to `src/models/export.py`**

Add after existing `Export` class:

```python
class BridgeReasonCode(StrEnum):
    """Reason codes for invalid bridge requests."""
    BRIDGE_RUN_NOT_FOUND = "BRIDGE_RUN_NOT_FOUND"
    BRIDGE_NO_RESULTS = "BRIDGE_NO_RESULTS"
    BRIDGE_SAME_RUN = "BRIDGE_SAME_RUN"
    BRIDGE_INCOMPATIBLE_RUNS = "BRIDGE_INCOMPATIBLE_RUNS"
    BRIDGE_NOT_FOUND = "BRIDGE_NOT_FOUND"


class VarianceBridgeAnalysis(ImpactOSBase):
    """Persisted variance bridge analysis record."""
    analysis_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    run_a_id: UUID
    run_b_id: UUID
    metric_type: str = Field(default="total_output", min_length=1, max_length=100)
    analysis_version: str = Field(default="bridge_v1", max_length=50)
    config_json: dict = Field(default_factory=dict)
    config_hash: str = Field(..., pattern=r"^sha256:[a-f0-9]{64}$")
    result_json: dict = Field(default_factory=dict)
    result_checksum: str = Field(..., pattern=r"^sha256:[a-f0-9]{64}$")
    created_at: UTCTimestamp = Field(default_factory=utc_now)
```

**Step 2: Implement AdvancedVarianceBridge in `src/export/variance_bridge.py`**

Add the new engine class alongside the existing `VarianceBridge` (do not remove it — legacy backward compat):

```python
"""Advanced artifact-linked variance bridge (Sprint 23).

Deterministic attribution from real RunSnapshot/ResultSet/ScenarioSpec diffs.
No LLM calls. Strict identity invariant.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field


class DriverType(StrEnum):
    """Variance driver categories — deterministic sort order."""
    PHASING = "PHASING"
    IMPORT_SHARE = "IMPORT_SHARE"
    MAPPING = "MAPPING"
    CONSTRAINT = "CONSTRAINT"
    MODEL_VERSION = "MODEL_VERSION"
    FEASIBILITY = "FEASIBILITY"
    RESIDUAL = "RESIDUAL"


@dataclass
class AdvancedVarianceDriver:
    """Single driver contribution with metadata."""
    driver_type: DriverType
    description: str
    impact: float
    raw_magnitude: float = 0.0
    weight: float = 0.0
    source_field: str | None = None
    diff_summary: str | None = None


@dataclass
class BridgeDiagnostics:
    """Structured diagnostics for audit trail."""
    checksum: str = ""
    tolerance_used: float = 1e-9
    identity_verified: bool = False
    driver_details: list[dict] = field(default_factory=list)


@dataclass
class BridgeResult:
    """Complete bridge output."""
    start_value: float
    end_value: float
    total_variance: float
    drivers: list[AdvancedVarianceDriver]
    diagnostics: BridgeDiagnostics


class AdvancedVarianceBridge:
    """Compute deterministic variance bridge from artifact diffs."""

    TOLERANCE = 1e-9

    @staticmethod
    def compute_from_artifacts(
        *,
        run_a_snapshot: dict,
        run_b_snapshot: dict,
        result_a: dict,
        result_b: dict,
        spec_a: dict | None = None,
        spec_b: dict | None = None,
        aggregate_key: str = "total",
    ) -> BridgeResult:
        # 1. Compute total variance
        start = result_a["values"][aggregate_key]
        end = result_b["values"][aggregate_key]
        total_variance = end - start

        # 2. Extract per-driver raw magnitudes
        changes: list[tuple[DriverType, str, float, str, str]] = []
        # (type, description, magnitude, source_field, diff_summary)

        # PHASING: time_horizon diff
        if spec_a and spec_b:
            th_a = spec_a.get("time_horizon", {})
            th_b = spec_b.get("time_horizon", {})
            if th_a != th_b:
                mag = _count_diffs(th_a, th_b)
                changes.append((DriverType.PHASING, "Phasing schedule adjusted",
                    mag, "time_horizon", f"{th_a} → {th_b}"))

        # IMPORT_SHARE: ImportSubstitution shock diffs
        if spec_a and spec_b:
            imp_a = [s for s in spec_a.get("shock_items", []) if s.get("type") == "ImportSubstitution"]
            imp_b = [s for s in spec_b.get("shock_items", []) if s.get("type") == "ImportSubstitution"]
            if imp_a != imp_b:
                mag = max(len(imp_a), len(imp_b), 1)
                changes.append((DriverType.IMPORT_SHARE, "Import share assumptions revised",
                    mag, "shock_items[ImportSubstitution]", f"{len(imp_a)} → {len(imp_b)} shocks"))

        # MAPPING: mapping_library_version_id diff
        ml_a = run_a_snapshot.get("mapping_library_version_id")
        ml_b = run_b_snapshot.get("mapping_library_version_id")
        if ml_a != ml_b:
            changes.append((DriverType.MAPPING, f"Mapping library updated ({ml_a} → {ml_b})",
                1.0, "mapping_library_version_id", f"{ml_a} → {ml_b}"))

        # CONSTRAINT: constraint_set_version_id diff
        cs_a = run_a_snapshot.get("constraint_set_version_id")
        cs_b = run_b_snapshot.get("constraint_set_version_id")
        if cs_a != cs_b:
            changes.append((DriverType.CONSTRAINT, f"Constraint set updated ({cs_a} → {cs_b})",
                1.0, "constraint_set_version_id", f"{cs_a} → {cs_b}"))

        # MODEL_VERSION: model_version_id diff
        mv_a = run_a_snapshot.get("model_version_id")
        mv_b = run_b_snapshot.get("model_version_id")
        if mv_a != mv_b:
            changes.append((DriverType.MODEL_VERSION, f"Model version changed ({mv_a} → {mv_b})",
                1.0, "model_version_id", f"{mv_a} → {mv_b}"))

        # FEASIBILITY: ConstraintOverride shock diffs
        if spec_a and spec_b:
            co_a = [s for s in spec_a.get("shock_items", []) if s.get("type") == "ConstraintOverride"]
            co_b = [s for s in spec_b.get("shock_items", []) if s.get("type") == "ConstraintOverride"]
            if co_a != co_b:
                mag = max(len(co_a), len(co_b), 1)
                changes.append((DriverType.FEASIBILITY, "Feasibility/constraint override effects",
                    mag, "shock_items[ConstraintOverride]", f"{len(co_a)} → {len(co_b)} overrides"))

        # 3. Compute attribution
        drivers: list[AdvancedVarianceDriver] = []
        total_magnitude = sum(c[2] for c in changes)

        if total_magnitude < TOLERANCE and abs(total_variance) > TOLERANCE:
            # All zero magnitudes + nonzero variance → 100% RESIDUAL
            drivers.append(AdvancedVarianceDriver(
                driver_type=DriverType.RESIDUAL,
                description="Unattributed variance (no detectable artifact diffs)",
                impact=total_variance,
                raw_magnitude=0.0,
                weight=1.0,
                source_field="residual",
            ))
        elif total_magnitude > 0:
            allocated = 0.0
            for dtype, desc, mag, src, diff in changes:
                w = mag / total_magnitude
                impact = total_variance * w
                drivers.append(AdvancedVarianceDriver(
                    driver_type=dtype, description=desc,
                    impact=impact, raw_magnitude=mag, weight=w,
                    source_field=src, diff_summary=diff,
                ))
                allocated += impact
            # Residual for identity
            residual = total_variance - allocated
            if abs(residual) > TOLERANCE:
                drivers.append(AdvancedVarianceDriver(
                    driver_type=DriverType.RESIDUAL,
                    description="Rounding residual",
                    impact=residual,
                    raw_magnitude=0.0, weight=0.0,
                    source_field="residual",
                ))

        # 4. Deterministic sort: enum order, then abs(impact) desc
        enum_order = list(DriverType)
        drivers.sort(key=lambda d: (enum_order.index(d.driver_type), -abs(d.impact)))

        # 5. Diagnostics
        driver_sum = sum(d.impact for d in drivers)
        identity_ok = abs(driver_sum - total_variance) < TOLERANCE

        canonical = json.dumps({
            "start": start, "end": end, "total_variance": total_variance,
            "drivers": [{"type": d.driver_type.value, "impact": d.impact} for d in drivers],
        }, sort_keys=True)
        checksum = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

        diagnostics = BridgeDiagnostics(
            checksum=checksum,
            tolerance_used=TOLERANCE,
            identity_verified=identity_ok,
            driver_details=[
                {"type": d.driver_type.value, "magnitude": d.raw_magnitude,
                 "weight": d.weight, "source": d.source_field}
                for d in drivers
            ],
        )

        return BridgeResult(
            start_value=start, end_value=end,
            total_variance=total_variance,
            drivers=drivers,
            diagnostics=diagnostics,
        )


def _count_diffs(a: dict, b: dict) -> float:
    """Count differing keys between two dicts."""
    all_keys = set(a.keys()) | set(b.keys())
    return sum(1.0 for k in all_keys if a.get(k) != b.get(k)) or 1.0


TOLERANCE = 1e-9
```

**Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/export/test_variance_bridge.py -v`

Expected: All tests pass (both old and new).

**Step 4: Commit**

```bash
git add src/export/variance_bridge.py src/models/export.py
git commit -m "[sprint23] implement deterministic advanced variance bridge attribution engine"
```

---

## Task 5: S23-2 — Write failing tests for persistence + API

**Files:**
- Modify: `tests/repositories/test_exports.py`
- Modify: `tests/api/test_exports.py`
- Modify: `tests/api/test_exports_quality_wiring.py`

**Step 1: Write failing repository tests**

Add to `tests/repositories/test_exports.py`:

```python
from src.repositories.exports import VarianceBridgeRepository

class TestVarianceBridgeRepository:
    """S23-2: Workspace-scoped bridge analytics persistence."""

    @pytest.fixture
    def bridge_repo(self, db_session):
        return VarianceBridgeRepository(db_session)

    async def test_create_and_get(self, bridge_repo, db_session):
        """Round-trip create and get."""
        analysis = _make_bridge_analysis(workspace_id=WS_ID)
        created = await bridge_repo.create(analysis)
        assert created.analysis_id == analysis.analysis_id
        fetched = await bridge_repo.get(WS_ID, analysis.analysis_id)
        assert fetched is not None
        assert fetched.config_hash == analysis.config_hash

    async def test_get_returns_none_for_wrong_workspace(self, bridge_repo, db_session):
        """Cross-workspace access returns None (surfaced as 404)."""
        analysis = _make_bridge_analysis(workspace_id=WS_ID)
        await bridge_repo.create(analysis)
        other_ws = uuid4()
        fetched = await bridge_repo.get(other_ws, analysis.analysis_id)
        assert fetched is None

    async def test_idempotent_create_by_config_hash(self, bridge_repo, db_session):
        """Duplicate config_hash returns existing record."""
        a1 = _make_bridge_analysis(workspace_id=WS_ID, config_hash="sha256:" + "a" * 64)
        a2 = _make_bridge_analysis(workspace_id=WS_ID, config_hash="sha256:" + "a" * 64)
        created1 = await bridge_repo.create(a1)
        created2 = await bridge_repo.create(a2)
        assert created1.analysis_id == created2.analysis_id

    async def test_list_for_workspace(self, bridge_repo, db_session):
        """List returns only workspace-scoped records."""
        a1 = _make_bridge_analysis(workspace_id=WS_ID)
        a2 = _make_bridge_analysis(workspace_id=WS_ID)
        a3 = _make_bridge_analysis(workspace_id=uuid4())  # different workspace
        await bridge_repo.create(a1)
        await bridge_repo.create(a2)
        await bridge_repo.create(a3)
        results = await bridge_repo.list_for_workspace(WS_ID)
        assert len(results) == 2


WS_ID = uuid4()

def _make_bridge_analysis(*, workspace_id, config_hash=None):
    from src.models.export import VarianceBridgeAnalysis
    import hashlib
    ch = config_hash or "sha256:" + hashlib.sha256(str(uuid4()).encode()).hexdigest()
    return VarianceBridgeAnalysis(
        workspace_id=workspace_id,
        run_a_id=uuid4(),
        run_b_id=uuid4(),
        metric_type="total_output",
        config_hash=ch,
        result_json={"drivers": []},
        result_checksum="sha256:" + "b" * 64,
    )
```

**Step 2: Write failing API tests**

Add to `tests/api/test_exports.py`:

```python
class TestVarianceBridgeAPI:
    """S23-2: Additive API for variance bridges."""

    async def test_create_bridge_returns_201(self, client, seeded_workspace):
        """POST /variance-bridges creates and returns bridge."""
        # Requires seeded runs in workspace
        resp = await client.post(
            f"/v1/workspaces/{seeded_workspace}/variance-bridges",
            json={"run_a_id": str(RUN_A_ID), "run_b_id": str(RUN_B_ID),
                  "metric_type": "total_output"},
        )
        assert resp.status_code == 201

    async def test_create_bridge_same_run_returns_422(self, client, seeded_workspace):
        """Same run_id for both returns 422 BRIDGE_SAME_RUN."""
        run_id = str(uuid4())
        resp = await client.post(
            f"/v1/workspaces/{seeded_workspace}/variance-bridges",
            json={"run_a_id": run_id, "run_b_id": run_id, "metric_type": "total_output"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["reason_code"] == "BRIDGE_SAME_RUN"

    async def test_get_bridge_returns_200(self, client, seeded_workspace, created_bridge):
        """GET /variance-bridges/{id} returns bridge."""
        resp = await client.get(
            f"/v1/workspaces/{seeded_workspace}/variance-bridges/{created_bridge}",
        )
        assert resp.status_code == 200

    async def test_get_bridge_wrong_workspace_returns_404(self, client, created_bridge):
        """Cross-workspace access returns 404."""
        other_ws = uuid4()
        resp = await client.get(
            f"/v1/workspaces/{other_ws}/variance-bridges/{created_bridge}",
        )
        assert resp.status_code == 404

    async def test_list_bridges_returns_200(self, client, seeded_workspace):
        """GET /variance-bridges returns list."""
        resp = await client.get(
            f"/v1/workspaces/{seeded_workspace}/variance-bridges",
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_legacy_endpoint_still_works(self, client, seeded_workspace):
        """POST /exports/variance-bridge still accepts free-form dicts."""
        resp = await client.post(
            f"/v1/workspaces/{seeded_workspace}/exports/variance-bridge",
            json={"run_a": {"total_impact": 100}, "run_b": {"total_impact": 120}},
        )
        assert resp.status_code == 200
```

**Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/repositories/test_exports.py::TestVarianceBridgeRepository tests/api/test_exports.py::TestVarianceBridgeAPI -v`

Expected: FAIL — `ImportError: cannot import name 'VarianceBridgeRepository'`

**Step 4: Commit failing tests**

```bash
git add tests/repositories/test_exports.py tests/api/test_exports.py tests/api/test_exports_quality_wiring.py
git commit -m "[sprint23] add failing tests for bridge persistence and additive api"
```

---

## Task 6: S23-2 — Implement persistence layer (table + migration + repository)

**Files:**
- Modify: `src/db/tables.py` (add `VarianceBridgeAnalysisRow`)
- Create: `alembic/versions/018_variance_bridge_analyses.py`
- Modify: `src/repositories/exports.py` (add `VarianceBridgeRepository`)

**Step 1: Add ORM model to `src/db/tables.py`**

Add after `WorkshopSessionRow`:

```python
class VarianceBridgeAnalysisRow(Base):
    """Workspace-scoped variance bridge analysis (Sprint 23)."""

    __tablename__ = "variance_bridge_analyses"
    __table_args__ = (
        UniqueConstraint("workspace_id", "config_hash", name="uq_vba_ws_config"),
    )

    analysis_id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.workspace_id"), nullable=False, index=True,
    )
    run_a_id: Mapped[UUID] = mapped_column(
        ForeignKey("run_snapshots.run_id"), nullable=False,
    )
    run_b_id: Mapped[UUID] = mapped_column(
        ForeignKey("run_snapshots.run_id"), nullable=False,
    )
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False)
    analysis_version: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="bridge_v1",
    )
    config_json = mapped_column(FlexJSON, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    result_json = mapped_column(FlexJSON, nullable=False)
    result_checksum: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
```

**Step 2: Create Alembic migration**

Create `alembic/versions/018_variance_bridge_analyses.py` following the pattern from `015_path_analyses.py`:

```python
"""018: Variance bridge analyses table (Sprint 23).

Revision ID: 018_variance_bridge_analyses
Revises: 017_workshop_sessions
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "018_variance_bridge_analyses"
down_revision = "017_workshop_sessions"

FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
FlexJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "variance_bridge_analyses",
        sa.Column("analysis_id", FlexUUID, primary_key=True),
        sa.Column("workspace_id", FlexUUID, sa.ForeignKey("workspaces.workspace_id"), nullable=False),
        sa.Column("run_a_id", FlexUUID, sa.ForeignKey("run_snapshots.run_id"), nullable=False),
        sa.Column("run_b_id", FlexUUID, sa.ForeignKey("run_snapshots.run_id"), nullable=False),
        sa.Column("metric_type", sa.String(100), nullable=False),
        sa.Column("analysis_version", sa.String(50), nullable=False, server_default="bridge_v1"),
        sa.Column("config_json", FlexJSON, nullable=False),
        sa.Column("config_hash", sa.String(100), nullable=False),
        sa.Column("result_json", FlexJSON, nullable=False),
        sa.Column("result_checksum", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "config_hash", name="uq_vba_ws_config"),
    )
    op.create_index("ix_vba_workspace_id", "variance_bridge_analyses", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_vba_workspace_id", table_name="variance_bridge_analyses")
    op.drop_table("variance_bridge_analyses")
```

**Step 3: Implement `VarianceBridgeRepository` in `src/repositories/exports.py`**

Add after existing `ExportRepository`:

```python
class VarianceBridgeRepository:
    """Workspace-scoped variance bridge analytics repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, analysis: VarianceBridgeAnalysis) -> VarianceBridgeAnalysis:
        """Create or return existing (idempotent by config_hash)."""
        # Check for existing
        existing = await self.get_by_config_hash(analysis.workspace_id, analysis.config_hash)
        if existing:
            return existing

        row = VarianceBridgeAnalysisRow(
            analysis_id=analysis.analysis_id,
            workspace_id=analysis.workspace_id,
            run_a_id=analysis.run_a_id,
            run_b_id=analysis.run_b_id,
            metric_type=analysis.metric_type,
            analysis_version=analysis.analysis_version,
            config_json=analysis.config_json,
            config_hash=analysis.config_hash,
            result_json=analysis.result_json,
            result_checksum=analysis.result_checksum,
            created_at=analysis.created_at,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_by_config_hash(analysis.workspace_id, analysis.config_hash)
            if existing:
                return existing
            raise
        return analysis

    async def get(self, workspace_id: UUID, analysis_id: UUID) -> VarianceBridgeAnalysis | None:
        """Get by ID, workspace-scoped."""
        stmt = select(VarianceBridgeAnalysisRow).where(
            VarianceBridgeAnalysisRow.analysis_id == analysis_id,
            VarianceBridgeAnalysisRow.workspace_id == workspace_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _row_to_bridge(row) if row else None

    async def get_by_config_hash(self, workspace_id: UUID, config_hash: str) -> VarianceBridgeAnalysis | None:
        """Get by config_hash, workspace-scoped."""
        stmt = select(VarianceBridgeAnalysisRow).where(
            VarianceBridgeAnalysisRow.workspace_id == workspace_id,
            VarianceBridgeAnalysisRow.config_hash == config_hash,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _row_to_bridge(row) if row else None

    async def list_for_workspace(
        self, workspace_id: UUID, *, limit: int = 50, offset: int = 0,
    ) -> list[VarianceBridgeAnalysis]:
        """List all bridges for workspace."""
        stmt = (
            select(VarianceBridgeAnalysisRow)
            .where(VarianceBridgeAnalysisRow.workspace_id == workspace_id)
            .order_by(VarianceBridgeAnalysisRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_bridge(r) for r in rows]


def _row_to_bridge(row: VarianceBridgeAnalysisRow) -> VarianceBridgeAnalysis:
    return VarianceBridgeAnalysis(
        analysis_id=row.analysis_id,
        workspace_id=row.workspace_id,
        run_a_id=row.run_a_id,
        run_b_id=row.run_b_id,
        metric_type=row.metric_type,
        analysis_version=row.analysis_version,
        config_json=row.config_json,
        config_hash=row.config_hash,
        result_json=row.result_json,
        result_checksum=row.result_checksum,
        created_at=row.created_at,
    )
```

**Step 4: Run repository tests**

Run: `python -m pytest tests/repositories/test_exports.py -v`

Expected: All pass.

**Step 5: Commit**

```bash
git add src/db/tables.py alembic/versions/018_variance_bridge_analyses.py src/repositories/exports.py
git commit -m "[sprint23] add variance bridge persistence layer with idempotent config hash"
```

---

## Task 7: S23-2 — Implement additive API endpoints

**Files:**
- Modify: `src/api/exports.py` (add 3 endpoints)
- Modify: `src/api/dependencies.py` (add DI for bridge repo)

**Step 1: Add DI function to `src/api/dependencies.py`**

Add after `get_workshop_session_repo` (around line 369):

```python
async def get_variance_bridge_repo(
    session: AsyncSession = Depends(get_async_session),
) -> "VarianceBridgeRepository":
    from src.repositories.exports import VarianceBridgeRepository
    return VarianceBridgeRepository(session)
```

**Step 2: Add request/response models and endpoints to `src/api/exports.py`**

Add new Pydantic models:

```python
class CreateBridgeRequest(BaseModel):
    run_a_id: UUID
    run_b_id: UUID
    metric_type: str = Field(default="total_output", min_length=1, max_length=100)

class BridgeDriverResponse(BaseModel):
    driver_type: str
    description: str
    impact: float
    raw_magnitude: float
    weight: float
    source_field: str | None = None
    diff_summary: str | None = None

class BridgeAnalysisResponse(BaseModel):
    analysis_id: str
    workspace_id: str
    run_a_id: str
    run_b_id: str
    metric_type: str
    analysis_version: str
    start_value: float
    end_value: float
    total_variance: float
    drivers: list[BridgeDriverResponse]
    config_hash: str
    result_checksum: str
    created_at: str

class BridgeErrorDetail(BaseModel):
    reason_code: str
    message: str
```

Add 3 endpoints (keep legacy `POST /exports/variance-bridge` unchanged):

```python
@router.post("/{workspace_id}/variance-bridges", status_code=201, response_model=BridgeAnalysisResponse)
async def create_variance_bridge(
    workspace_id: UUID,
    body: CreateBridgeRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    bridge_repo: VarianceBridgeRepository = Depends(get_variance_bridge_repo),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    result_repo: ResultSetRepository = Depends(get_result_set_repo),
) -> BridgeAnalysisResponse:
    """Compute + persist a variance bridge between two runs."""
    # Validation...
    # Fetch artifacts...
    # Compute bridge...
    # Persist...
    # Return...

@router.get("/{workspace_id}/variance-bridges/{analysis_id}", response_model=BridgeAnalysisResponse)
async def get_variance_bridge(
    workspace_id: UUID,
    analysis_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    bridge_repo: VarianceBridgeRepository = Depends(get_variance_bridge_repo),
) -> BridgeAnalysisResponse:
    """Get a single variance bridge analysis."""

@router.get("/{workspace_id}/variance-bridges", response_model=list[BridgeAnalysisResponse])
async def list_variance_bridges(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    bridge_repo: VarianceBridgeRepository = Depends(get_variance_bridge_repo),
    limit: int = 50,
    offset: int = 0,
) -> list[BridgeAnalysisResponse]:
    """List variance bridges for a workspace."""
```

**Step 3: Add `get_result_set_repo` DI if needed**

Check if it exists already in `src/api/dependencies.py` (it does at line 191). Import it in exports.py if not already imported.

**Step 4: Run API tests**

Run: `python -m pytest tests/api/test_exports.py tests/api/test_exports_quality_wiring.py -v`

Expected: All pass.

**Step 5: Run full backend test suite**

Run: `python -m pytest tests --ignore=tests/migration -q`

Expected: All pass. No regressions.

**Step 6: Commit**

```bash
git add src/api/exports.py src/api/dependencies.py
git commit -m "[sprint23] persist workspace-scoped variance bridge analytics with additive api"
```

---

## Task 8: S23-3 — Write failing frontend tests

**Files:**
- Create: `frontend/src/components/exports/__tests__/WaterfallChart.test.tsx`
- Create: `frontend/src/components/exports/__tests__/DriverCard.test.tsx`
- Create: `frontend/src/components/exports/__tests__/RunSelector.test.tsx`
- Modify: `frontend/src/lib/api/hooks/useExports.ts` (tests for new hooks)

**Step 1: Write component tests**

`WaterfallChart.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { WaterfallChart } from '../WaterfallChart';

describe('WaterfallChart', () => {
  const mockDrivers = [
    { driver_type: 'PHASING', description: 'Phasing adjusted', impact: 10.0, raw_magnitude: 1, weight: 0.5 },
    { driver_type: 'MAPPING', description: 'Mapping updated', impact: 10.0, raw_magnitude: 1, weight: 0.5 },
  ];

  it('renders start and end values', () => {
    render(<WaterfallChart startValue={100} endValue={120} totalVariance={20} drivers={mockDrivers} />);
    expect(screen.getByText(/100/)).toBeInTheDocument();
    expect(screen.getByText(/120/)).toBeInTheDocument();
  });

  it('renders driver bars', () => {
    render(<WaterfallChart startValue={100} endValue={120} totalVariance={20} drivers={mockDrivers} />);
    expect(screen.getByText(/Phasing/i)).toBeInTheDocument();
    expect(screen.getByText(/Mapping/i)).toBeInTheDocument();
  });

  it('shows positive impacts in green', () => {
    const { container } = render(
      <WaterfallChart startValue={100} endValue={120} totalVariance={20} drivers={mockDrivers} />,
    );
    // Check for green-colored elements
    expect(container.querySelector('[data-positive="true"]')).toBeInTheDocument();
  });

  it('handles empty drivers', () => {
    render(<WaterfallChart startValue={100} endValue={100} totalVariance={0} drivers={[]} />);
    expect(screen.getByText(/no variance/i)).toBeInTheDocument();
  });
});
```

`DriverCard.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { DriverCard } from '../DriverCard';

describe('DriverCard', () => {
  it('renders driver type badge', () => {
    render(<DriverCard driverType="PHASING" description="Phasing adjusted" impact={10.5} weight={0.5} />);
    expect(screen.getByText('PHASING')).toBeInTheDocument();
  });

  it('renders impact value', () => {
    render(<DriverCard driverType="MAPPING" description="Mapping updated" impact={-5.3} weight={0.3} />);
    expect(screen.getByText(/-5\.3/)).toBeInTheDocument();
  });

  it('renders percentage of total', () => {
    render(<DriverCard driverType="RESIDUAL" description="Residual" impact={2.0} weight={0.1} totalVariance={20} />);
    expect(screen.getByText(/10%/)).toBeInTheDocument();
  });
});
```

`RunSelector.test.tsx`:
```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { RunSelector } from '../RunSelector';

describe('RunSelector', () => {
  const mockRuns = [
    { run_id: 'r1', label: 'Run 1', created_at: '2026-03-01' },
    { run_id: 'r2', label: 'Run 2', created_at: '2026-03-02' },
  ];

  it('renders dropdowns for run A and run B', () => {
    render(<RunSelector runs={mockRuns} onCompare={vi.fn()} />);
    expect(screen.getByLabelText(/run a/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/run b/i)).toBeInTheDocument();
  });

  it('disables compare button when same run selected', () => {
    render(<RunSelector runs={mockRuns} onCompare={vi.fn()} />);
    // Select same run for both
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'r1' } });
    fireEvent.change(selects[1], { target: { value: 'r1' } });
    expect(screen.getByRole('button', { name: /compare/i })).toBeDisabled();
  });

  it('calls onCompare with selected run IDs', () => {
    const onCompare = vi.fn();
    render(<RunSelector runs={mockRuns} onCompare={onCompare} />);
    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'r1' } });
    fireEvent.change(selects[1], { target: { value: 'r2' } });
    fireEvent.click(screen.getByRole('button', { name: /compare/i }));
    expect(onCompare).toHaveBeenCalledWith('r1', 'r2');
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/exports/__tests__`

Expected: FAIL — modules not found.

**Step 3: Commit failing tests**

```bash
git add frontend/src/components/exports/__tests__/
git commit -m "[sprint23] add failing tests for boardroom variance bridge components"
```

---

## Task 9: S23-3 — Implement frontend components and pages

**Files:**
- Create: `frontend/src/components/exports/WaterfallChart.tsx`
- Create: `frontend/src/components/exports/DriverCard.tsx`
- Create: `frontend/src/components/exports/RunSelector.tsx`
- Modify: `frontend/src/lib/api/hooks/useExports.ts` (add bridge hooks)
- Modify: `frontend/src/lib/api/schema.ts` (add bridge types)
- Create: `frontend/src/app/w/[workspaceId]/exports/compare/page.tsx`
- Create: `frontend/src/app/w/[workspaceId]/exports/bridges/[analysisId]/page.tsx`
- Modify: `frontend/src/app/w/[workspaceId]/exports/page.tsx` (add CTA)

**Step 1: Add TypeScript types to `schema.ts`**

```typescript
// Variance Bridge (Sprint 23)
CreateVarianceBridgeRequest: {
  run_a_id: string;
  run_b_id: string;
  metric_type?: string;
}

BridgeDriverResponse: {
  driver_type: string;
  description: string;
  impact: number;
  raw_magnitude: number;
  weight: number;
  source_field?: string | null;
  diff_summary?: string | null;
}

BridgeAnalysisResponse: {
  analysis_id: string;
  workspace_id: string;
  run_a_id: string;
  run_b_id: string;
  metric_type: string;
  analysis_version: string;
  start_value: number;
  end_value: number;
  total_variance: number;
  drivers: BridgeDriverResponse[];
  config_hash: string;
  result_checksum: string;
  created_at: string;
}
```

**Step 2: Add hooks to `useExports.ts`**

```typescript
export function useCreateVarianceBridge(workspaceId: string) {
  return useMutation<BridgeAnalysisResponse, Error, CreateVarianceBridgeRequest>({
    mutationFn: async (body) => {
      const resp = await fetch(`/api/v1/workspaces/${workspaceId}/variance-bridges`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`Bridge creation failed: ${resp.status}`);
      return resp.json();
    },
  });
}

export function useVarianceBridge(workspaceId: string, analysisId: string) {
  return useQuery<BridgeAnalysisResponse>({
    queryKey: ['variance-bridge', workspaceId, analysisId],
    queryFn: async () => {
      const resp = await fetch(`/api/v1/workspaces/${workspaceId}/variance-bridges/${analysisId}`);
      if (!resp.ok) throw new Error(`Bridge fetch failed: ${resp.status}`);
      return resp.json();
    },
    enabled: !!analysisId,
  });
}

export function useVarianceBridges(workspaceId: string) {
  return useQuery<BridgeAnalysisResponse[]>({
    queryKey: ['variance-bridges', workspaceId],
    queryFn: async () => {
      const resp = await fetch(`/api/v1/workspaces/${workspaceId}/variance-bridges`);
      if (!resp.ok) throw new Error(`Bridge list failed: ${resp.status}`);
      return resp.json();
    },
  });
}
```

**Step 3: Implement components**

Create `WaterfallChart.tsx`, `DriverCard.tsx`, `RunSelector.tsx` using existing design system patterns. Each component should:
- Use Tailwind CSS (matches existing codebase)
- Include proper ARIA labels
- Handle loading/error/empty states

**Step 4: Create compare page**

`frontend/src/app/w/[workspaceId]/exports/compare/page.tsx`:
- Run selector with two dropdowns
- Metric type selector (default total_output)
- Compare button
- Results area showing waterfall + driver cards on success

**Step 5: Create bridge detail page**

`frontend/src/app/w/[workspaceId]/exports/bridges/[analysisId]/page.tsx`:
- Fetch bridge by ID
- Render waterfall + driver cards
- Show metadata: timestamps, model versions, workspace context

**Step 6: Add CTA links to exports page**

Modify `frontend/src/app/w/[workspaceId]/exports/page.tsx`:
- Add "Compare Runs" button/link that navigates to `/exports/compare`

**Step 7: Run frontend tests**

Run: `cd frontend && npx vitest run`

Expected: All pass including new component tests.

**Step 8: Commit**

```bash
git add frontend/src/
git commit -m "[sprint23] add boardroom variance explainability frontend flows"
```

---

## Task 10: S23-4 — Docs, evidence, and contract sync

**Files:**
- Modify: `docs/ImpactOS_Master_Build_Plan_v2.md`
- Modify: `docs/plans/2026-03-03-full-system-completion-master-plan.md`
- Modify: `docs/evidence/release-readiness-checklist.md`
- Regenerate: `openapi.json`

**Step 1: Update tracker docs**

Add MVP-23 row to Master Build Plan with test count and commit hash.

Update full-system-completion-master-plan with Sprint 23 in Wave B completion table.

Add variance bridge evidence section to release-readiness-checklist with:
- Driver attribution matrix
- API reason-code matrix
- Frontend coverage matrix
- Migration normalization evidence

**Step 2: Regenerate OpenAPI**

Run: `python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"`
Run: `python -c "import json; json.load(open('openapi.json', 'r', encoding='utf-8')); print('openapi.json valid')"`

Expected: Valid JSON, new variance-bridge endpoints present.

**Step 3: Run full verification**

Run all verification commands from Sprint 23 prompt:

```powershell
python -m pytest tests/migration/test_012_runseries_postgres.py tests/migration/test_013_sg_provenance_postgres.py tests/migration/test_014_assumption_workspace_postgres.py tests/migration/test_015_path_analyses_postgres.py tests/migration/test_016_portfolio_optimization_postgres.py tests/migration/test_017_workshop_sessions_postgres.py -q
python -m pytest tests/export/test_variance_bridge.py tests/api/test_exports.py tests/api/test_exports_quality_wiring.py tests/repositories/test_exports.py -q
python -m pytest tests/engine/test_batch.py tests/engine/test_runseries.py tests/integration/test_path_doc_to_export.py -q
cd frontend && pnpm install && npx vitest run && cd ..
python -m pytest tests --ignore=tests/migration -q
python -m alembic current
python -m alembic check
```

**Step 4: Commit**

```bash
git add docs/ openapi.json
git commit -m "[sprint23] add mvp23 evidence and refresh openapi"
```

---

## Task 11: Code review + PR

**Step 1: Request code review**

Use `superpowers:requesting-code-review` skill.

**Step 2: Apply review findings**

Use `superpowers:receiving-code-review` skill.

**Step 3: Push and create PR**

```bash
git push -u origin phase3-sprint23-advanced-variance-bridges
gh pr create --title "[sprint23] Advanced Variance Bridges + Explainability (MVP-23)" --body "..."
```

---

## Commit Message Sequence

1. `[sprint23] add shared migration test helper with single DSN policy`
2. `[sprint23] normalize migration test dsn and ownership policy for 012-017`
3. `[sprint23] add failing tests for advanced variance bridge attribution engine`
4. `[sprint23] implement deterministic advanced variance bridge attribution engine`
5. `[sprint23] add failing tests for bridge persistence and additive api`
6. `[sprint23] persist workspace-scoped variance bridge analytics with additive api`
7. `[sprint23] add failing tests for boardroom variance bridge components`
8. `[sprint23] add boardroom variance explainability frontend flows`
9. `[sprint23] add mvp23 evidence and refresh openapi`

---

## Verification Checklist

Before claiming done:

- [ ] `MIGRATION_TEST_DSN` env var drives all migration tests (no hardcoded creds)
- [ ] CI mode fails hard when DSN unset
- [ ] Advanced bridge engine: strict identity verified
- [ ] Bridge is directional (config_hash preserves run_a/run_b order)
- [ ] Zero magnitudes → 100% RESIDUAL
- [ ] Deterministic driver sort (enum order + abs tie-break)
- [ ] Persistence: idempotent by config_hash
- [ ] API: 404 for cross-workspace (not 403)
- [ ] Legacy endpoint unchanged
- [ ] Frontend: compare page with run selectors (no raw UUID entry)
- [ ] Frontend: CTA links on exports/runs pages
- [ ] OpenAPI regenerated and valid
- [ ] All backend tests pass
- [ ] All frontend tests pass
- [ ] No regressions in existing test suite
