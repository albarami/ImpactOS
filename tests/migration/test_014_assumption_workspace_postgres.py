"""Gate 2: Real Postgres migration proof for migration 014 (assumption workspace_id).

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or Postgres unreachable.
"""

import os
import subprocess
import sys

import pytest

_SKIP_PG = os.environ.get("IMPACTOS_SKIP_PG_MIGRATION", "0") == "1"

_PG_DSN = "postgresql://impactos:impactos@localhost:5432/impactos"
_ALEMBIC_DSN = "postgresql+asyncpg://impactos:impactos@localhost:5432/impactos"


def _pg_reachable() -> bool:
    """Quick check if Postgres is reachable."""
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import asyncio, asyncpg\n"
             "async def _probe():\n"
             f"    c = await asyncpg.connect('{_PG_DSN}', timeout=3)\n"
             "    await c.close()\n"
             "asyncio.run(_probe())\n"],
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


def _alembic_env() -> dict[str, str]:
    """Build env dict for alembic subprocesses with correct DATABASE_URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = _ALEMBIC_DSN
    return env


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True, text=True, timeout=30,
        env=_alembic_env(),
    )


def _column_exists(table: str, column: str) -> bool:
    """Check if a column exists on a Postgres table via asyncpg."""
    check_script = (
        "import asyncio, asyncpg\n"
        "async def check():\n"
        f"    conn = await asyncpg.connect('{_PG_DSN}', timeout=3)\n"
        "    try:\n"
        f"        val = await conn.fetchval(\n"
        f"            \"SELECT column_name FROM information_schema.columns \"\n"
        f"            \"WHERE table_name = '{table}' AND column_name = '{column}'\"\n"
        f"        )\n"
        "        print('EXISTS' if val else 'MISSING')\n"
        "    finally:\n"
        "        await conn.close()\n"
        "asyncio.run(check())\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", check_script],
        capture_output=True, text=True, timeout=10,
    )
    return "EXISTS" in r.stdout


class TestMigration014Postgres:
    def test_upgrade_adds_column(self):
        """Upgrade to head; verify workspace_id column exists on assumptions."""
        r = _run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"
        assert _column_exists("assumptions", "workspace_id"), (
            "workspace_id column not found on assumptions table after upgrade"
        )

    def test_downgrade_removes_column(self):
        """Downgrade -1; verify workspace_id column is gone."""
        _run_alembic("upgrade", "head")
        r = _run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"
        assert not _column_exists("assumptions", "workspace_id"), (
            "workspace_id column still present on assumptions after downgrade"
        )

    def test_re_upgrade(self):
        """Downgrade then re-upgrade; verify clean."""
        _run_alembic("upgrade", "head")
        _run_alembic("downgrade", "-1")
        r = _run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed:\n{r.stderr}"
        assert _column_exists("assumptions", "workspace_id"), (
            "workspace_id column not found after re-upgrade"
        )

    def test_alembic_check_no_drift(self):
        """After upgrade to head, alembic check reports no new operations."""
        _run_alembic("upgrade", "head")
        r = _run_alembic("check")
        assert r.returncode == 0, f"drift detected:\n{r.stderr}"
