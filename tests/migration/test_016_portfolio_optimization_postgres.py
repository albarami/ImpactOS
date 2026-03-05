"""Gate 2: Real Postgres migration proof for migration 016 (portfolio_optimizations).

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


class TestMigration016Postgres:
    def test_upgrade_creates_table(self):
        """Upgrade to head; verify portfolio_optimizations table exists with expected columns."""
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"
        assert table_exists("portfolio_optimizations"), (
            "portfolio_optimizations table not found after upgrade"
        )
        cols = get_columns("portfolio_optimizations")
        expected = {
            "portfolio_id",
            "workspace_id",
            "model_version_id",
            "optimization_version",
            "config_json",
            "config_hash",
            "objective_metric",
            "cost_metric",
            "budget",
            "min_selected",
            "max_selected",
            "candidate_run_ids_json",
            "selected_run_ids_json",
            "result_json",
            "result_checksum",
            "created_at",
        }
        assert expected.issubset(set(cols)), f"Missing columns: {expected - set(cols)}"

    def test_unique_constraint(self):
        """Duplicate (workspace_id, config_hash) raises IntegrityError."""
        run_alembic("upgrade", "head")

        ws_id = str(uuid.uuid4())
        mv_id = str(uuid.uuid4())

        # Insert workspace
        exec_sql(
            f"INSERT INTO workspaces (workspace_id, client_name, engagement_code, "
            f"classification, description, created_by, created_at, updated_at) "
            f"VALUES ('{ws_id}', 'test', 'T001', 'internal', '', "
            f"'{ws_id}', NOW(), NOW())"
        )

        # First insert should succeed
        pid1 = str(uuid.uuid4())
        result1 = exec_sql(
            f"INSERT INTO portfolio_optimizations (portfolio_id, workspace_id, "
            f"model_version_id, optimization_version, config_json, config_hash, "
            f"objective_metric, cost_metric, budget, min_selected, max_selected, "
            f"candidate_run_ids_json, selected_run_ids_json, result_json, "
            f"result_checksum, created_at) "
            f"VALUES ('{pid1}', '{ws_id}', '{mv_id}', '1.0.0', '{{}}', "
            f"'hash123', 'total_output', 'total_cost', 1000000.0, 2, 5, "
            f"'[]', '[]', '{{}}', 'chk1', NOW())"
        )
        assert "OK" in result1, f"First insert failed: {result1}"

        # Second insert with same (workspace_id, config_hash) should fail
        pid2 = str(uuid.uuid4())
        result2 = exec_sql(
            f"INSERT INTO portfolio_optimizations (portfolio_id, workspace_id, "
            f"model_version_id, optimization_version, config_json, config_hash, "
            f"objective_metric, cost_metric, budget, min_selected, max_selected, "
            f"candidate_run_ids_json, selected_run_ids_json, result_json, "
            f"result_checksum, created_at) "
            f"VALUES ('{pid2}', '{ws_id}', '{mv_id}', '1.0.0', '{{}}', "
            f"'hash123', 'total_output', 'total_cost', 1000000.0, 2, 5, "
            f"'[]', '[]', '{{}}', 'chk2', NOW())"
        )
        assert "ERROR" in result2, f"Expected unique violation, got: {result2}"
        assert (
            "UniqueViolation" in result2
            or "IntegrityError" in result2
            or "unique" in result2.lower()
        ), f"Expected unique constraint error, got: {result2}"

    def test_downgrade_removes_table(self):
        """Table removed cleanly after downgrade to 015_path_analyses."""
        run_alembic("upgrade", "head")
        assert table_exists("portfolio_optimizations"), "Table should exist before downgrade"
        r = run_alembic("downgrade", "015_path_analyses")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"
        assert not table_exists("portfolio_optimizations"), (
            "portfolio_optimizations table still present after downgrade"
        )

    def test_re_upgrade(self):
        """Downgrade to 015_path_analyses then re-upgrade; verify clean state."""
        run_alembic("upgrade", "head")
        run_alembic("downgrade", "015_path_analyses")
        assert not table_exists("portfolio_optimizations"), (
            "Table should not exist after downgrade"
        )
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}"
        assert table_exists("portfolio_optimizations"), (
            "portfolio_optimizations table not found after re-upgrade"
        )
