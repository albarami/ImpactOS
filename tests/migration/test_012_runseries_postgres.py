"""Gate 2: Real Postgres migration proof for migration 012 (RunSeries columns).

Requires a running PostgreSQL instance. Set DATABASE_URL env var or uses the
default from src.config.settings.

Tests:
  1. upgrade head (applies all migrations including 012)
  2. downgrade -1 (reverts 012)
  3. upgrade head (re-applies 012)
  4. alembic check (no drift between models and migrations)
  5. Constraint enforcement (CHECK + partial unique indexes)

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or Postgres unreachable.
"""

import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import pytest

# Skip if explicitly disabled or Postgres not reachable
_SKIP_PG = os.environ.get("IMPACTOS_SKIP_PG_MIGRATION", "0") == "1"


def _pg_reachable() -> bool:
    """Check if Postgres is reachable and credentials work."""
    try:
        import asyncpg

        async def _check():
            from src.config.settings import get_settings
            s = get_settings()
            url = s.DATABASE_URL.replace("postgresql+asyncpg://", "")
            # Parse user:pw@host:port/db
            userinfo, hostinfo = url.split("@", 1)
            user, pw = userinfo.split(":", 1) if ":" in userinfo else (userinfo, "")
            hostport, db = hostinfo.split("/", 1)
            host, port = hostport.split(":", 1) if ":" in hostport else (hostport, "5432")
            conn = await asyncpg.connect(
                host=host, port=int(port), user=user, password=pw,
                database=db, timeout=3,
            )
            await conn.close()
            return True

        return asyncio.run(_check())
    except Exception:
        return False


_PG_AVAILABLE = not _SKIP_PG and _pg_reachable()
pytestmark = pytest.mark.skipif(
    not _PG_AVAILABLE,
    reason="Postgres not reachable or IMPACTOS_SKIP_PG_MIGRATION=1",
)


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestMigration012Postgres:
    """Real Postgres migration cycle for migration 012."""

    def test_upgrade_head(self):
        r = _run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade head failed:\n{r.stderr}"

    def test_downgrade_one(self):
        # Ensure at head first
        _run_alembic("upgrade", "head")
        r = _run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade -1 failed:\n{r.stderr}"

    def test_re_upgrade_head(self):
        # Downgrade first, then re-upgrade
        _run_alembic("upgrade", "head")
        _run_alembic("downgrade", "-1")
        r = _run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade head failed:\n{r.stderr}"

    def test_alembic_check_no_drift(self):
        _run_alembic("upgrade", "head")
        r = _run_alembic("check")
        # alembic check returns 0 if no new migrations needed
        assert r.returncode == 0, f"alembic check detected drift:\n{r.stderr}"

    def test_check_constraint_series_kind_enum(self):
        """CHECK chk_series_kind blocks invalid series_kind values."""
        import asyncpg

        async def _test():
            from src.config.settings import get_settings
            s = get_settings()
            url = s.DATABASE_URL.replace("+asyncpg", "").replace("postgresql://", "")
            userinfo, hostinfo = url.split("@", 1)
            user, pw = userinfo.split(":", 1)
            hostport, db = hostinfo.split("/", 1)
            host, port = hostport.split(":", 1)

            conn = await asyncpg.connect(
                host=host, port=int(port), user=user, password=pw, database=db,
            )
            try:
                _run_alembic("upgrade", "head")
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
            from src.config.settings import get_settings
            s = get_settings()
            url = s.DATABASE_URL.replace("+asyncpg", "").replace("postgresql://", "")
            userinfo, hostinfo = url.split("@", 1)
            user, pw = userinfo.split(":", 1)
            hostport, db = hostinfo.split("/", 1)
            host, port = hostport.split(":", 1)

            conn = await asyncpg.connect(
                host=host, port=int(port), user=user, password=pw, database=db,
            )
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
            from src.config.settings import get_settings
            s = get_settings()
            url = s.DATABASE_URL.replace("+asyncpg", "").replace("postgresql://", "")
            userinfo, hostinfo = url.split("@", 1)
            user, pw = userinfo.split(":", 1)
            hostport, db = hostinfo.split("/", 1)
            host, port = hostport.split(":", 1)

            conn = await asyncpg.connect(
                host=host, port=int(port), user=user, password=pw, database=db,
            )
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
