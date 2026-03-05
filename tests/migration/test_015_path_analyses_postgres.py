"""Gate 2: Real Postgres migration proof for migration 015 (path_analyses).

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


class TestMigration015Postgres:
    def test_upgrade_creates_table(self):
        """Upgrade to head; verify path_analyses table exists with expected columns."""
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"
        assert table_exists("path_analyses"), "path_analyses table not found after upgrade"
        cols = get_columns("path_analyses")
        expected = {
            "analysis_id",
            "run_id",
            "workspace_id",
            "analysis_version",
            "config_json",
            "config_hash",
            "max_depth",
            "top_k",
            "top_paths_json",
            "chokepoints_json",
            "depth_contributions_json",
            "coverage_ratio",
            "result_checksum",
            "created_at",
        }
        assert expected.issubset(set(cols)), f"Missing columns: {expected - set(cols)}"

    def test_unique_constraint_enforced(self):
        """Duplicate (run_id, config_hash) raises IntegrityError."""
        run_alembic("upgrade", "head")

        # We need valid FK references — insert minimal workspace + run_snapshot first
        ws_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # Insert workspace
        exec_sql(
            f"INSERT INTO workspaces (workspace_id, client_name, engagement_code, "
            f"classification, description, created_by, created_at, updated_at) "
            f"VALUES ('{ws_id}', 'test', 'T001', 'internal', '', "
            f"'{ws_id}', NOW(), NOW())"
        )

        # Insert run_snapshot
        exec_sql(
            f"INSERT INTO run_snapshots (run_id, model_version_id, taxonomy_version_id, "
            f"concordance_version_id, mapping_library_version_id, "
            f"assumption_library_version_id, prompt_pack_version_id, "
            f"source_checksums, created_at, workspace_id) "
            f"VALUES ('{run_id}', '{uuid.uuid4()}', '{uuid.uuid4()}', "
            f"'{uuid.uuid4()}', '{uuid.uuid4()}', '{uuid.uuid4()}', "
            f"'{uuid.uuid4()}', '{{}}', NOW(), '{ws_id}')"
        )

        # First insert should succeed
        aid1 = str(uuid.uuid4())
        result1 = exec_sql(
            f"INSERT INTO path_analyses (analysis_id, run_id, workspace_id, "
            f"analysis_version, config_json, config_hash, max_depth, top_k, "
            f"top_paths_json, chokepoints_json, depth_contributions_json, "
            f"coverage_ratio, result_checksum, created_at) "
            f"VALUES ('{aid1}', '{run_id}', '{ws_id}', '1.0.0', '{{}}', "
            f"'hash123', 5, 10, '[]', '[]', '[]', 0.85, 'chk1', NOW())"
        )
        assert "OK" in result1, f"First insert failed: {result1}"

        # Second insert with same (run_id, config_hash) should fail
        aid2 = str(uuid.uuid4())
        result2 = exec_sql(
            f"INSERT INTO path_analyses (analysis_id, run_id, workspace_id, "
            f"analysis_version, config_json, config_hash, max_depth, top_k, "
            f"top_paths_json, chokepoints_json, depth_contributions_json, "
            f"coverage_ratio, result_checksum, created_at) "
            f"VALUES ('{aid2}', '{run_id}', '{ws_id}', '1.0.0', '{{}}', "
            f"'hash123', 5, 10, '[]', '[]', '[]', 0.85, 'chk2', NOW())"
        )
        assert "ERROR" in result2, f"Expected unique violation, got: {result2}"
        assert (
            "UniqueViolation" in result2
            or "IntegrityError" in result2
            or "unique" in result2.lower()
        ), f"Expected unique constraint error, got: {result2}"

    def test_coverage_check_constraint(self):
        """coverage_ratio=1.5 raises on Postgres (CHECK constraint)."""
        run_alembic("upgrade", "head")

        ws_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        exec_sql(
            f"INSERT INTO workspaces (workspace_id, client_name, engagement_code, "
            f"classification, description, created_by, created_at, updated_at) "
            f"VALUES ('{ws_id}', 'test', 'T002', 'internal', '', "
            f"'{ws_id}', NOW(), NOW())"
        )
        exec_sql(
            f"INSERT INTO run_snapshots (run_id, model_version_id, taxonomy_version_id, "
            f"concordance_version_id, mapping_library_version_id, "
            f"assumption_library_version_id, prompt_pack_version_id, "
            f"source_checksums, created_at, workspace_id) "
            f"VALUES ('{run_id}', '{uuid.uuid4()}', '{uuid.uuid4()}', "
            f"'{uuid.uuid4()}', '{uuid.uuid4()}', '{uuid.uuid4()}', "
            f"'{uuid.uuid4()}', '{{}}', NOW(), '{ws_id}')"
        )

        aid = str(uuid.uuid4())
        result = exec_sql(
            f"INSERT INTO path_analyses (analysis_id, run_id, workspace_id, "
            f"analysis_version, config_json, config_hash, max_depth, top_k, "
            f"top_paths_json, chokepoints_json, depth_contributions_json, "
            f"coverage_ratio, result_checksum, created_at) "
            f"VALUES ('{aid}', '{run_id}', '{ws_id}', '1.0.0', '{{}}', "
            f"'hash_bad', 5, 10, '[]', '[]', '[]', 1.5, 'chk_bad', NOW())"
        )
        assert "ERROR" in result, f"Expected check violation, got: {result}"
        assert "CheckViolation" in result or "check" in result.lower(), (
            f"Expected check constraint error, got: {result}"
        )

    def test_downgrade_drops_table(self):
        """Table removed cleanly after downgrade."""
        run_alembic("upgrade", "head")
        assert table_exists("path_analyses"), "Table should exist before downgrade"
        r = run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"
        assert not table_exists("path_analyses"), (
            "path_analyses table still present after downgrade"
        )
