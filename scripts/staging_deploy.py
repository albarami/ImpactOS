"""Staging deployment prerequisite checker and command generator.

Usage:
    # Check prerequisites from env file
    python scripts/staging_deploy.py check [--env-file .env.staging]

    # Generate deployment commands
    python scripts/staging_deploy.py commands [--env-file .env.staging]

    # Full check + command output as JSON
    python scripts/staging_deploy.py check --json [--env-file .env.staging]

Exit code: 0 if all prerequisites met, 1 if any fail.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PrereqResult:
    """Single prerequisite check result."""

    name: str
    status: str  # PASS, FAIL
    detail: str


@dataclass
class DeployReport:
    """Aggregated deployment prerequisite report."""

    overall: str  # PASS or FAIL
    env_file: str
    checks: list[PrereqResult] = field(default_factory=list)

    def has_failures(self) -> bool:
        """Return True if any check has FAIL status."""
        return any(c.status == "FAIL" for c in self.checks)


# ---------------------------------------------------------------------------
# Environment file parser
# ---------------------------------------------------------------------------

# Patterns that indicate dev/placeholder values
_DEV_SECRET_KEY = "dev-secret-change-in-production"
_PLACEHOLDER_DB_PATTERNS = ("changeme", "localhost")
_PLACEHOLDER_PATTERNS = ("REPLACE_", "YOUR_", "YOUR-", "CHANGE_ME")


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse a .env file into a dict of key=value pairs.

    Handles:
    - Comments (lines starting with #)
    - Empty lines
    - Quoted values (single or double)
    - Inline comments after values
    """
    env: dict[str, str] = {}
    filepath = Path(path)

    if not filepath.exists():
        return env

    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Remove inline comments (but not inside quotes)
        if not value.startswith(("'", '"')):
            value = value.split("#")[0].strip()

        # Remove surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        env[key] = value

    return env


def _is_placeholder(value: str) -> bool:
    """Check if a value looks like a placeholder."""
    upper = value.upper()
    return any(p in upper for p in _PLACEHOLDER_PATTERNS)


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------


def check_env_file_exists(env_file: str) -> PrereqResult:
    """Check that the env file exists."""
    if Path(env_file).exists():
        return PrereqResult(
            name="env_file_exists",
            status="PASS",
            detail=f"{env_file} exists",
        )
    return PrereqResult(
        name="env_file_exists",
        status="FAIL",
        detail=f"{env_file} not found — copy from .env.staging.example",
    )


def check_environment_value(env: dict[str, str]) -> PrereqResult:
    """Check ENVIRONMENT is set to staging or prod."""
    value = env.get("ENVIRONMENT", "")
    if value in ("staging", "prod"):
        return PrereqResult(
            name="environment",
            status="PASS",
            detail=f"ENVIRONMENT={value}",
        )
    return PrereqResult(
        name="environment",
        status="FAIL",
        detail=f"ENVIRONMENT={value!r} — must be 'staging' or 'prod'",
    )


def check_secret_key(env: dict[str, str]) -> PrereqResult:
    """Check SECRET_KEY is set and not the dev default."""
    value = env.get("SECRET_KEY", "")
    if not value:
        return PrereqResult(
            name="secret_key",
            status="FAIL",
            detail="SECRET_KEY is empty — generate with: python -c \"import secrets; print(secrets.token_urlsafe(64))\"",
        )
    if value == _DEV_SECRET_KEY:
        return PrereqResult(
            name="secret_key",
            status="FAIL",
            detail="SECRET_KEY uses dev default — set a real secret",
        )
    if _is_placeholder(value):
        return PrereqResult(
            name="secret_key",
            status="FAIL",
            detail="SECRET_KEY contains placeholder text — set a real secret",
        )
    if len(value) < 32:
        return PrereqResult(
            name="secret_key",
            status="FAIL",
            detail=f"SECRET_KEY is only {len(value)} chars — use at least 32",
        )
    return PrereqResult(
        name="secret_key",
        status="PASS",
        detail=f"SECRET_KEY set ({len(value)} chars)",
    )


def check_database_url(env: dict[str, str]) -> PrereqResult:
    """Check DATABASE_URL is set and not a placeholder."""
    value = env.get("DATABASE_URL", "")
    if not value:
        return PrereqResult(
            name="database_url",
            status="FAIL",
            detail="DATABASE_URL is empty",
        )
    for pattern in _PLACEHOLDER_DB_PATTERNS:
        if pattern in value.lower():
            return PrereqResult(
                name="database_url",
                status="FAIL",
                detail=f"DATABASE_URL contains '{pattern}' — use real credentials",
            )
    if _is_placeholder(value):
        return PrereqResult(
            name="database_url",
            status="FAIL",
            detail="DATABASE_URL contains placeholder text — use real credentials",
        )
    return PrereqResult(
        name="database_url",
        status="PASS",
        detail="DATABASE_URL set (non-placeholder)",
    )


def check_object_storage(env: dict[str, str]) -> PrereqResult:
    """Check OBJECT_STORAGE_PATH is absolute or S3."""
    value = env.get("OBJECT_STORAGE_PATH", "")
    if not value:
        return PrereqResult(
            name="object_storage",
            status="FAIL",
            detail="OBJECT_STORAGE_PATH is empty",
        )
    # Accept absolute paths (/, C:\), S3 URIs, and other scheme URIs
    is_absolute = value.startswith("/") or (len(value) >= 3 and value[1] == ":")
    is_uri = "://" in value
    if not is_absolute and not is_uri:
        return PrereqResult(
            name="object_storage",
            status="FAIL",
            detail=f"OBJECT_STORAGE_PATH={value!r} — must be absolute path or S3 URI in staging",
        )
    return PrereqResult(
        name="object_storage",
        status="PASS",
        detail=f"OBJECT_STORAGE_PATH={value}",
    )


def check_idp_config(env: dict[str, str]) -> PrereqResult:
    """Check IdP variables (JWT_ISSUER, JWT_AUDIENCE, JWKS_URL) are set."""
    missing = []
    for var in ("JWT_ISSUER", "JWT_AUDIENCE", "JWKS_URL"):
        val = env.get(var, "")
        if not val or _is_placeholder(val):
            missing.append(var)

    if missing:
        return PrereqResult(
            name="idp_config",
            status="FAIL",
            detail=f"Missing or placeholder IdP config: {', '.join(missing)}",
        )
    return PrereqResult(
        name="idp_config",
        status="PASS",
        detail="JWT_ISSUER, JWT_AUDIENCE, JWKS_URL all set",
    )


def check_minio_credentials(env: dict[str, str]) -> PrereqResult:
    """Check MinIO/S3 credentials are non-dev."""
    access = env.get("MINIO_ACCESS_KEY", "")
    secret = env.get("MINIO_SECRET_KEY", "")

    if not access or not secret:
        return PrereqResult(
            name="minio_credentials",
            status="FAIL",
            detail="MINIO_ACCESS_KEY or MINIO_SECRET_KEY is empty",
        )
    if access == "impactos" and secret == "impactos-secret":
        return PrereqResult(
            name="minio_credentials",
            status="FAIL",
            detail="MinIO credentials are dev defaults — use staging credentials",
        )
    if _is_placeholder(access) or _is_placeholder(secret):
        return PrereqResult(
            name="minio_credentials",
            status="FAIL",
            detail="MinIO credentials contain placeholder text",
        )
    return PrereqResult(
        name="minio_credentials",
        status="PASS",
        detail="MinIO credentials set (non-dev)",
    )


def check_frontend_config(env: dict[str, str]) -> PrereqResult:
    """Check frontend staging prerequisites (NEXTAUTH_SECRET, OIDC vars).

    Returns SKIP if no frontend vars are present (frontend not deployed).
    Returns PASS if all required vars are set and non-placeholder.
    Returns FAIL if any required var is missing, dev default, or placeholder.
    """
    _DEV_NEXTAUTH_SECRET = "dev-secret-do-not-use-in-production"
    _FRONTEND_VARS = ("NEXTAUTH_SECRET", "NEXTAUTH_PROVIDER", "NEXTAUTH_URL",
                      "OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET")

    # If no frontend vars at all, frontend is not being deployed
    has_any = any(env.get(v) for v in _FRONTEND_VARS)
    if not has_any:
        return PrereqResult(
            name="frontend_config",
            status="SKIP",
            detail="No frontend env vars present — frontend not included in deployment",
        )

    # NEXTAUTH_SECRET is always required
    secret = env.get("NEXTAUTH_SECRET", "")
    if not secret:
        return PrereqResult(
            name="frontend_config",
            status="FAIL",
            detail="NEXTAUTH_SECRET is empty — required for session encryption",
        )
    if secret == _DEV_NEXTAUTH_SECRET:
        return PrereqResult(
            name="frontend_config",
            status="FAIL",
            detail="NEXTAUTH_SECRET is dev default — set a real secret",
        )
    if _is_placeholder(secret):
        return PrereqResult(
            name="frontend_config",
            status="FAIL",
            detail="NEXTAUTH_SECRET contains placeholder text",
        )

    # If provider is OIDC, check OIDC vars
    provider = env.get("NEXTAUTH_PROVIDER", "credentials")
    if provider == "oidc":
        missing = []
        for var in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"):
            val = env.get(var, "")
            if not val:
                missing.append(var)
            elif _is_placeholder(val):
                missing.append(f"{var} (placeholder)")
        if missing:
            return PrereqResult(
                name="frontend_config",
                status="FAIL",
                detail=f"Missing or placeholder OIDC config: {', '.join(missing)}",
            )

    return PrereqResult(
        name="frontend_config",
        status="PASS",
        detail=f"Frontend config valid (provider={provider})",
    )


def check_postgres_credentials(env: dict[str, str]) -> PrereqResult:
    """Check POSTGRES_USER/PASSWORD are non-dev."""
    user = env.get("POSTGRES_USER", "")
    password = env.get("POSTGRES_PASSWORD", "")

    if not user or not password:
        return PrereqResult(
            name="postgres_credentials",
            status="FAIL",
            detail="POSTGRES_USER or POSTGRES_PASSWORD is empty",
        )
    if user == "impactos" and password == "impactos":
        return PrereqResult(
            name="postgres_credentials",
            status="FAIL",
            detail="Postgres credentials are dev defaults — use staging credentials",
        )
    if _is_placeholder(password):
        return PrereqResult(
            name="postgres_credentials",
            status="FAIL",
            detail="POSTGRES_PASSWORD contains placeholder text",
        )
    return PrereqResult(
        name="postgres_credentials",
        status="PASS",
        detail=f"Postgres credentials set (user={user})",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_checks(env_file: str) -> DeployReport:
    """Run all prerequisite checks against an env file."""
    checks: list[PrereqResult] = []

    # Check 1: env file exists
    file_check = check_env_file_exists(env_file)
    checks.append(file_check)

    if file_check.status == "FAIL":
        return DeployReport(overall="FAIL", env_file=env_file, checks=checks)

    # Parse the env file
    env = parse_env_file(env_file)

    # Check 2-8: backend prerequisites
    checks.append(check_environment_value(env))
    checks.append(check_secret_key(env))
    checks.append(check_database_url(env))
    checks.append(check_object_storage(env))
    checks.append(check_idp_config(env))
    checks.append(check_minio_credentials(env))
    checks.append(check_postgres_credentials(env))

    # Check 9: frontend prerequisites (SKIP if not deploying frontend)
    checks.append(check_frontend_config(env))

    has_fail = any(c.status == "FAIL" for c in checks)
    return DeployReport(
        overall="FAIL" if has_fail else "PASS",
        env_file=env_file,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# Command generator
# ---------------------------------------------------------------------------


def generate_commands(env_file: str) -> list[str]:
    """Generate the deployment command sequence."""
    return [
        f"# Step 1: Validate prerequisites",
        f"python scripts/staging_deploy.py check --env-file {env_file}",
        f"",
        f"# Step 2: Build and start stack with staging overlay",
        f"docker compose -f docker-compose.yml -f docker-compose.staging.yml "
        f"--env-file {env_file} up -d --build",
        f"",
        f"# Step 3: Wait for API health",
        f"docker compose exec api python -c "
        f"\"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\"",
        f"",
        f"# Step 4: Run migrations",
        f"docker compose exec api alembic upgrade head",
        f"",
        f"# Step 5: Verify migration state",
        f"docker compose exec api alembic current",
        f"docker compose exec api alembic check",
        f"",
        f"# Step 6: Run preflight",
        f"docker compose exec api python scripts/staging_preflight.py "
        f"--url http://localhost:8000",
        f"",
        f"# Step 7: Run smoke tests",
        f"python scripts/staging_smoke.py --url http://localhost:8000",
    ]


# ---------------------------------------------------------------------------
# CLI output helpers
# ---------------------------------------------------------------------------


_STATUS_SYMBOLS = {"PASS": "[PASS]", "FAIL": "[FAIL]"}


def _print_table(report: DeployReport) -> None:
    """Print a human-readable table of results."""
    max_name = max(len(c.name) for c in report.checks) if report.checks else 10
    print()
    print(f"Prerequisite Check: {report.env_file}")
    print(f"{'Check':<{max_name + 2}} {'Status':<8} Detail")
    print("-" * (max_name + 2 + 8 + 50))
    for c in report.checks:
        symbol = _STATUS_SYMBOLS.get(c.status, c.status)
        print(f"{c.name:<{max_name + 2}} {symbol:<8} {c.detail}")
    print()
    print(f"Overall: {report.overall}")
    print()


def _print_json(report: DeployReport) -> None:
    """Print JSON report to stdout."""
    print(json.dumps(asdict(report), indent=2))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and run checks or generate commands."""
    parser = argparse.ArgumentParser(
        description="Staging deployment prerequisite checker.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-command")

    # check sub-command
    check_parser = subparsers.add_parser(
        "check", help="Check staging prerequisites"
    )
    check_parser.add_argument(
        "--env-file",
        type=str,
        default=".env.staging",
        help="Path to staging env file (default: .env.staging)",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output structured JSON report",
    )

    # commands sub-command
    cmd_parser = subparsers.add_parser(
        "commands", help="Generate deployment commands"
    )
    cmd_parser.add_argument(
        "--env-file",
        type=str,
        default=".env.staging",
        help="Path to staging env file (default: .env.staging)",
    )

    args = parser.parse_args()

    if args.command == "check":
        report = run_checks(env_file=args.env_file)
        if args.json_output:
            _print_json(report)
        else:
            _print_table(report)
        sys.exit(1 if report.has_failures() else 0)

    elif args.command == "commands":
        commands = generate_commands(env_file=args.env_file)
        for cmd in commands:
            print(cmd)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
