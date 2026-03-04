"""Gate 2: Real Postgres migration proof for migration 015 (path_analyses).

Skip condition: IMPACTOS_SKIP_PG_MIGRATION=1 or Postgres unreachable.
"""

import os
import subprocess
import sys
import uuid

import pytest

_SKIP_PG = os.environ.get("IMPACTOS_SKIP_PG_MIGRATION", "0") == "1"

_PG_DSN = "postgresql://postgres:Salim1977@localhost:5432/impactos"
_ALEMBIC_DSN = "postgresql+asyncpg://postgres:Salim1977@localhost:5432/impactos"


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


def _table_exists(table: str) -> bool:
    """Check if a table exists on Postgres via asyncpg."""
    check_script = (
        "import asyncio, asyncpg\n"
        "async def check():\n"
        f"    conn = await asyncpg.connect('{_PG_DSN}', timeout=3)\n"
        "    try:\n"
        f"        val = await conn.fetchval(\n"
        f"            \"SELECT table_name FROM information_schema.tables \"\n"
        f"            \"WHERE table_name = '{table}'\"\n"
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


def _get_columns(table: str) -> list[str]:
    """Return column names for a table via asyncpg."""
    check_script = (
        "import asyncio, asyncpg\n"
        "async def check():\n"
        f"    conn = await asyncpg.connect('{_PG_DSN}', timeout=3)\n"
        "    try:\n"
        f"        rows = await conn.fetch(\n"
        f"            \"SELECT column_name FROM information_schema.columns \"\n"
        f"            \"WHERE table_name = '{table}' ORDER BY ordinal_position\"\n"
        f"        )\n"
        "        print(','.join(r['column_name'] for r in rows))\n"
        "    finally:\n"
        "        await conn.close()\n"
        "asyncio.run(check())\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", check_script],
        capture_output=True, text=True, timeout=10,
    )
    if r.stdout.strip():
        return r.stdout.strip().split(",")
    return []


def _exec_sql(sql: str) -> str:
    """Execute arbitrary SQL via asyncpg, return stdout."""
    script = (
        "import asyncio, asyncpg\n"
        "async def run():\n"
        f"    conn = await asyncpg.connect('{_PG_DSN}', timeout=3)\n"
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
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip()


class TestMigration015Postgres:
    def test_upgrade_creates_table(self):
        """Upgrade to head; verify path_analyses table exists with expected columns."""
        r = _run_alembic("upgrade", "head")
        assert r.returncode == 0, f"upgrade failed:\n{r.stderr}"
        assert _table_exists("path_analyses"), (
            "path_analyses table not found after upgrade"
        )
        cols = _get_columns("path_analyses")
        expected = {
            "analysis_id", "run_id", "workspace_id", "analysis_version",
            "config_json", "config_hash", "max_depth", "top_k",
            "top_paths_json", "chokepoints_json", "depth_contributions_json",
            "coverage_ratio", "result_checksum", "created_at",
        }
        assert expected.issubset(set(cols)), (
            f"Missing columns: {expected - set(cols)}"
        )

    def test_unique_constraint_enforced(self):
        """Duplicate (run_id, config_hash) raises IntegrityError."""
        _run_alembic("upgrade", "head")

        # We need valid FK references — insert minimal workspace + run_snapshot first
        ws_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # Insert workspace
        _exec_sql(
            f"INSERT INTO workspaces (workspace_id, client_name, engagement_code, "
            f"classification, description, created_by, created_at, updated_at) "
            f"VALUES ('{ws_id}', 'test', 'T001', 'internal', '', "
            f"'{ws_id}', NOW(), NOW())"
        )

        # Insert run_snapshot
        _exec_sql(
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
        result1 = _exec_sql(
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
        result2 = _exec_sql(
            f"INSERT INTO path_analyses (analysis_id, run_id, workspace_id, "
            f"analysis_version, config_json, config_hash, max_depth, top_k, "
            f"top_paths_json, chokepoints_json, depth_contributions_json, "
            f"coverage_ratio, result_checksum, created_at) "
            f"VALUES ('{aid2}', '{run_id}', '{ws_id}', '1.0.0', '{{}}', "
            f"'hash123', 5, 10, '[]', '[]', '[]', 0.85, 'chk2', NOW())"
        )
        assert "ERROR" in result2, f"Expected unique violation, got: {result2}"
        assert "UniqueViolation" in result2 or "IntegrityError" in result2 or "unique" in result2.lower(), (
            f"Expected unique constraint error, got: {result2}"
        )

    def test_coverage_check_constraint(self):
        """coverage_ratio=1.5 raises on Postgres (CHECK constraint)."""
        _run_alembic("upgrade", "head")

        ws_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        _exec_sql(
            f"INSERT INTO workspaces (workspace_id, client_name, engagement_code, "
            f"classification, description, created_by, created_at, updated_at) "
            f"VALUES ('{ws_id}', 'test', 'T002', 'internal', '', "
            f"'{ws_id}', NOW(), NOW())"
        )
        _exec_sql(
            f"INSERT INTO run_snapshots (run_id, model_version_id, taxonomy_version_id, "
            f"concordance_version_id, mapping_library_version_id, "
            f"assumption_library_version_id, prompt_pack_version_id, "
            f"source_checksums, created_at, workspace_id) "
            f"VALUES ('{run_id}', '{uuid.uuid4()}', '{uuid.uuid4()}', "
            f"'{uuid.uuid4()}', '{uuid.uuid4()}', '{uuid.uuid4()}', "
            f"'{uuid.uuid4()}', '{{}}', NOW(), '{ws_id}')"
        )

        aid = str(uuid.uuid4())
        result = _exec_sql(
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
        _run_alembic("upgrade", "head")
        assert _table_exists("path_analyses"), "Table should exist before downgrade"
        r = _run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade failed:\n{r.stderr}"
        assert not _table_exists("path_analyses"), (
            "path_analyses table still present after downgrade"
        )
