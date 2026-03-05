"""Gate 2: Real Postgres migration proof for migration 014 (assumption workspace_id).

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or MIGRATION_TEST_DSN not set
or Postgres unreachable.
"""

import pytest

from tests.migration.pg_migration_helpers import (
    column_exists,
    pg_skip_marker,
    run_alembic,
)

pytestmark = pg_skip_marker


class TestMigration014Postgres:
    def test_upgrade_adds_column(self):
        """Upgrade to head; verify workspace_id column exists on assumptions."""
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"
        assert column_exists("assumptions", "workspace_id"), (
            "workspace_id column not found on assumptions table after upgrade"
        )

    def test_downgrade_removes_column(self):
        """Downgrade to 013_sg_provenance; verify workspace_id column is gone."""
        run_alembic("upgrade", "head")
        r = run_alembic("downgrade", "013_sg_provenance")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"
        assert not column_exists("assumptions", "workspace_id"), (
            "workspace_id column still present on assumptions after downgrade"
        )

    def test_re_upgrade(self):
        """Downgrade to 013_sg_provenance then re-upgrade; verify clean."""
        run_alembic("upgrade", "head")
        run_alembic("downgrade", "013_sg_provenance")
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}"
        assert column_exists("assumptions", "workspace_id"), (
            "workspace_id column not found after re-upgrade"
        )

    def test_alembic_check_no_drift(self):
        """After upgrade to head, alembic check reports no new operations."""
        run_alembic("upgrade", "head")
        r = run_alembic("check")
        assert r.returncode == 0, f"drift detected:\n{r.stderr}"
