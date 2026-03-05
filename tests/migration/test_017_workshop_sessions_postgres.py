"""Gate 2: Real Postgres migration proof for migration 017 (workshop_sessions).

Tests:
  1. upgrade head creates workshop_sessions with correct columns
  2. UNIQUE (workspace_id, config_hash) enforced
  3. CHECK status IN ('draft', 'committed', 'archived') enforced
  4. downgrade to 016 removes table
  5. re-upgrade restores table cleanly
  6. alembic check detects no drift

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or MIGRATION_TEST_DSN not set
or Postgres unreachable.
"""

import uuid

import pytest

from tests.migration.pg_migration_helpers import (
    exec_sql,
    get_columns,
    pg_skip_marker,
    run_alembic,
    table_exists,
)

pytestmark = pg_skip_marker


class TestMigration017Postgres:
    def test_upgrade_creates_table(self) -> None:
        """Upgrade to head; verify workshop_sessions table exists with expected columns."""
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"
        assert table_exists("workshop_sessions"), (
            "workshop_sessions table not found after upgrade"
        )
        cols = get_columns("workshop_sessions")
        expected = {
            "session_id",
            "workspace_id",
            "baseline_run_id",
            "base_shocks_json",
            "slider_config_json",
            "transformed_shocks_json",
            "config_hash",
            "committed_run_id",
            "status",
            "preview_summary_json",
            "created_by",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(set(cols)), f"Missing columns: {expected - set(cols)}"

    def test_unique_constraint(self) -> None:
        """Duplicate (workspace_id, config_hash) raises IntegrityError."""
        run_alembic("upgrade", "head")

        ws_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        mv_id = str(uuid.uuid4())

        # Ensure workspace and run exist for FKs
        exec_sql(
            f"INSERT INTO workspaces (workspace_id, client_name, engagement_code, "
            f"classification, description, created_by, created_at, updated_at) "
            f"VALUES ('{ws_id}', 'test', 'T017', 'internal', '', "
            f"'{ws_id}', NOW(), NOW())"
        )
        exec_sql(
            f"INSERT INTO run_snapshots (run_id, workspace_id, "
            f"model_version_id, taxonomy_version_id, concordance_version_id, "
            f"mapping_library_version_id, assumption_library_version_id, "
            f"prompt_pack_version_id, source_checksums, created_at) "
            f"VALUES ('{run_id}', '{ws_id}', '{mv_id}', '{mv_id}', '{mv_id}', "
            f"'{mv_id}', '{mv_id}', '{mv_id}', '{{}}', NOW())"
        )

        # First insert should succeed
        sid1 = str(uuid.uuid4())
        result1 = exec_sql(
            f"INSERT INTO workshop_sessions (session_id, workspace_id, "
            f"baseline_run_id, base_shocks_json, slider_config_json, "
            f"transformed_shocks_json, config_hash, status, created_at, updated_at) "
            f"VALUES ('{sid1}', '{ws_id}', '{run_id}', '{{}}', '[]', "
            f"'{{}}', 'hash017', 'draft', NOW(), NOW())"
        )
        assert "OK" in result1, f"First insert failed: {result1}"

        # Second insert with same (workspace_id, config_hash) should fail
        sid2 = str(uuid.uuid4())
        result2 = exec_sql(
            f"INSERT INTO workshop_sessions (session_id, workspace_id, "
            f"baseline_run_id, base_shocks_json, slider_config_json, "
            f"transformed_shocks_json, config_hash, status, created_at, updated_at) "
            f"VALUES ('{sid2}', '{ws_id}', '{run_id}', '{{}}', '[]', "
            f"'{{}}', 'hash017', 'draft', NOW(), NOW())"
        )
        assert "ERROR" in result2, f"Expected unique violation, got: {result2}"
        assert (
            "UniqueViolation" in result2
            or "IntegrityError" in result2
            or "unique" in result2.lower()
        ), f"Expected unique constraint error, got: {result2}"

    def test_check_constraint_status(self) -> None:
        """CHECK constraint blocks invalid status values."""
        run_alembic("upgrade", "head")

        ws_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        mv_id = str(uuid.uuid4())

        exec_sql(
            f"INSERT INTO workspaces (workspace_id, client_name, engagement_code, "
            f"classification, description, created_by, created_at, updated_at) "
            f"VALUES ('{ws_id}', 'test', 'T017c', 'internal', '', "
            f"'{ws_id}', NOW(), NOW())"
        )
        exec_sql(
            f"INSERT INTO run_snapshots (run_id, workspace_id, "
            f"model_version_id, taxonomy_version_id, concordance_version_id, "
            f"mapping_library_version_id, assumption_library_version_id, "
            f"prompt_pack_version_id, source_checksums, created_at) "
            f"VALUES ('{run_id}', '{ws_id}', '{mv_id}', '{mv_id}', '{mv_id}', "
            f"'{mv_id}', '{mv_id}', '{mv_id}', '{{}}', NOW())"
        )

        # Insert with invalid status should fail
        sid = str(uuid.uuid4())
        result = exec_sql(
            f"INSERT INTO workshop_sessions (session_id, workspace_id, "
            f"baseline_run_id, base_shocks_json, slider_config_json, "
            f"transformed_shocks_json, config_hash, status, created_at, updated_at) "
            f"VALUES ('{sid}', '{ws_id}', '{run_id}', '{{}}', '[]', "
            f"'{{}}', 'hash017chk', 'INVALID_STATUS', NOW(), NOW())"
        )
        assert "ERROR" in result, f"Expected check violation, got: {result}"
        assert (
            "CheckViolation" in result
            or "check" in result.lower()
        ), f"Expected check constraint error, got: {result}"

    def test_downgrade_removes_table(self) -> None:
        """Table removed cleanly after downgrade to 016_portfolio_optimizations."""
        run_alembic("upgrade", "head")
        assert table_exists("workshop_sessions"), "Table should exist before downgrade"
        r = run_alembic("downgrade", "016_portfolio_optimizations")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"
        assert not table_exists("workshop_sessions"), (
            "workshop_sessions table still present after downgrade"
        )

    def test_re_upgrade(self) -> None:
        """Downgrade to 016 then re-upgrade; verify clean state."""
        run_alembic("upgrade", "head")
        run_alembic("downgrade", "016_portfolio_optimizations")
        assert not table_exists("workshop_sessions"), (
            "Table should not exist after downgrade"
        )
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}"
        assert table_exists("workshop_sessions"), (
            "workshop_sessions table not found after re-upgrade"
        )

    def test_alembic_check_no_drift(self) -> None:
        """No ORM-migration drift at head."""
        run_alembic("upgrade", "head")
        r = run_alembic("check")
        assert r.returncode == 0, f"alembic check detected drift:\n{r.stderr}"
