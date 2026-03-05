"""Gate 2: Real Postgres migration proof for migration 012 (RunSeries columns).

Requires a running PostgreSQL instance. Set MIGRATION_TEST_DSN env var.

Tests:
  1. upgrade head (applies all migrations including 012)
  2. downgrade -1 (reverts 012)
  3. upgrade head (re-applies 012)
  4. alembic check (no drift between models and migrations)
  5. Constraint enforcement (CHECK + partial unique indexes)

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or MIGRATION_TEST_DSN not set
or Postgres unreachable.
"""

import asyncio
from uuid import uuid4

import pytest

from tests.migration.pg_migration_helpers import (
    _dsn_for_asyncpg,
    pg_skip_marker,
    run_alembic,
)

pytestmark = pg_skip_marker


class TestMigration012Postgres:
    """Real Postgres migration cycle for migration 012."""

    def test_upgrade_head(self):
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}"

    def test_downgrade_one(self):
        # Ensure at head first
        run_alembic("upgrade", "head")
        r = run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade -1 failed:\n{r.stderr}"

    def test_re_upgrade_head(self):
        # Downgrade first, then re-upgrade
        run_alembic("upgrade", "head")
        run_alembic("downgrade", "-1")
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade head failed:\n{r.stderr}"

    def test_alembic_check_no_drift(self):
        run_alembic("upgrade", "head")
        r = run_alembic("check")
        # alembic check returns 0 if no new migrations needed
        assert r.returncode == 0, f"alembic check detected drift:\n{r.stderr}"

    def test_check_constraint_series_kind_enum(self):
        """CHECK chk_series_kind blocks invalid series_kind values."""
        import asyncpg

        async def _test():
            dsn = _dsn_for_asyncpg()
            conn = await asyncpg.connect(dsn)
            try:
                run_alembic("upgrade", "head")
                rid = uuid4()
                run_id = uuid4()
                # Insert with invalid series_kind should fail
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(
                        """INSERT INTO result_sets
                           (result_id, run_id, metric_type, values, sector_breakdowns,
                            series_kind, year, created_at)
                           VALUES ($1, $2, 'test', '{}', '{}', 'INVALID', 2026, NOW())""",
                        rid, run_id,
                    )
            finally:
                await conn.close()

        asyncio.run(_test())

    def test_check_constraint_year_required(self):
        """CHECK chk_year_required enforces year/series_kind coupling."""
        import asyncpg

        async def _test():
            dsn = _dsn_for_asyncpg()
            conn = await asyncpg.connect(dsn)
            try:
                # series_kind='annual' but year=NULL should fail
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(
                        """INSERT INTO result_sets
                           (result_id, run_id, metric_type, values, sector_breakdowns,
                            series_kind, year, created_at)
                           VALUES ($1, $2, 'test', '{}', '{}', 'annual', NULL, NOW())""",
                        uuid4(), uuid4(),
                    )
            finally:
                await conn.close()

        asyncio.run(_test())

    def test_partial_unique_index_blocks_duplicate_annual(self):
        """Partial unique index uq_resultset_annual blocks duplicate annual rows."""
        import asyncpg

        async def _test():
            dsn = _dsn_for_asyncpg()
            conn = await asyncpg.connect(dsn)
            try:
                run_id = uuid4()
                # Insert first annual row — should succeed
                await conn.execute(
                    """INSERT INTO result_sets
                       (result_id, run_id, metric_type, values, sector_breakdowns,
                        series_kind, year, created_at)
                       VALUES ($1, $2, 'total_output', '{"A": 1.0}', '{}', 'annual', 2026, NOW())""",
                    uuid4(), run_id,
                )
                # Insert duplicate (same run, metric, year) — should fail
                with pytest.raises(asyncpg.UniqueViolationError):
                    await conn.execute(
                        """INSERT INTO result_sets
                           (result_id, run_id, metric_type, values, sector_breakdowns,
                            series_kind, year, created_at)
                           VALUES ($1, $2, 'total_output', '{"A": 2.0}', '{}', 'annual', 2026, NOW())""",
                        uuid4(), run_id,
                    )
            finally:
                # Clean up
                await conn.execute("DELETE FROM result_sets WHERE run_id = $1", run_id)
                await conn.close()

        asyncio.run(_test())
