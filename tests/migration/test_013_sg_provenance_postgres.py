"""Gate 2: Real Postgres migration proof for migration 013 (sg_provenance).

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or MIGRATION_TEST_DSN not set
or Postgres unreachable.
"""

import pytest

from tests.migration.pg_migration_helpers import pg_skip_marker, run_alembic

pytestmark = pg_skip_marker


class TestMigration013Postgres:
    def test_upgrade_head(self):
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"

    def test_downgrade_one(self):
        run_alembic("upgrade", "head")
        r = run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"

    def test_re_upgrade(self):
        run_alembic("upgrade", "head")
        run_alembic("downgrade", "-1")
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}"

    def test_alembic_check_no_drift(self):
        run_alembic("upgrade", "head")
        r = run_alembic("check")
        assert r.returncode == 0, f"drift detected:\n{r.stderr}"
