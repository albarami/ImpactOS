"""Gate 2: Real Postgres migration proof for migration 013 (sg_provenance).

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or Postgres unreachable.
"""

import os
import subprocess
import sys

import pytest

_SKIP_PG = os.environ.get("IMPACTOS_SKIP_PG_MIGRATION", "0") == "1"


def _pg_reachable() -> bool:
    """Quick check if Postgres is reachable."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import asyncio, asyncpg; "
             "asyncio.run(asyncpg.connect("
             "'postgresql://impactos:impactos@localhost:5432/impactos', timeout=3).close())"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
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
        capture_output=True, text=True, timeout=30,
    )


class TestMigration013Postgres:
    def test_upgrade_head(self):
        r = _run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"

    def test_downgrade_one(self):
        _run_alembic("upgrade", "head")
        r = _run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"

    def test_re_upgrade(self):
        _run_alembic("upgrade", "head")
        _run_alembic("downgrade", "-1")
        r = _run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}"

    def test_alembic_check_no_drift(self):
        _run_alembic("upgrade", "head")
        r = _run_alembic("check")
        assert r.returncode == 0, f"drift detected:\n{r.stderr}"
