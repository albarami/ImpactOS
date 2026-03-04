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
