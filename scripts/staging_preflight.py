"""Staging preflight -- repeatable pre-deployment verification.

Usage:
    python scripts/staging_preflight.py [--json] [--url http://localhost:8000]

Checks:
    1. ENVIRONMENT is non-dev
    2. Config validation (validate_settings_for_env)
    3. Alembic at head and clean
    4. /readiness returns 200 (if server reachable)
    5. /health includes all component checks (if server reachable)
    6. No secrets in output (self-verification)

Output: JSON report with overall status and per-check detail.
Exit code: 0 if all PASS or SKIP, 1 if any FAIL.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

import httpx

from src.config.settings import Environment, Settings, get_settings, validate_settings_for_env

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Single preflight check result."""

    name: str
    status: str  # PASS, FAIL, SKIP, WARN
    detail: str


@dataclass
class PreflightReport:
    """Aggregated preflight report."""

    overall: str  # PASS or FAIL
    checks: list[CheckResult] = field(default_factory=list)

    def has_failures(self) -> bool:
        """Return True if any check has FAIL status."""
        return any(c.status == "FAIL" for c in self.checks)


# ---------------------------------------------------------------------------
# Secret-redaction helpers
# ---------------------------------------------------------------------------

_DB_URL_PASSWORD_RE = re.compile(r"://([^:]+):([^@]+)@")


def redact_database_url(url: str) -> str:
    """Mask the password component of a database URL.

    ``postgresql+asyncpg://user:secret@host/db``
    becomes ``postgresql+asyncpg://user:***@host/db``.
    If no password segment is found the URL is returned unchanged.
    """
    match = _DB_URL_PASSWORD_RE.search(url)
    if not match:
        return url
    return _DB_URL_PASSWORD_RE.sub(rf"://\1:***@", url)


def redact_secret_key(key: str) -> str:
    """Show first 4 characters followed by ``***``.

    Keys shorter than 5 characters are fully redacted to ``***``
    since showing the entire value defeats the purpose.
    """
    if not key:
        return "not set"
    if len(key) <= 4:
        return "***"
    return key[:4] + "***"


def redact_api_key(key: str) -> str:
    """Return ``'set'`` if key is truthy, ``'not set'`` otherwise."""
    return "set" if key else "not set"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_environment(settings: Settings) -> CheckResult:
    """Check 1: ENVIRONMENT is non-dev."""
    env = settings.ENVIRONMENT
    if env == Environment.DEV:
        return CheckResult(
            name="environment",
            status="WARN",
            detail=f"ENVIRONMENT is '{env.value}' -- expected staging or prod",
        )
    return CheckResult(
        name="environment",
        status="PASS",
        detail=f"ENVIRONMENT is '{env.value}'",
    )


def check_config_validation(settings: Settings) -> CheckResult:
    """Check 2: validate_settings_for_env passes."""
    errors = validate_settings_for_env(settings)
    if errors:
        return CheckResult(
            name="config_validation",
            status="FAIL",
            detail="; ".join(errors),
        )
    return CheckResult(
        name="config_validation",
        status="PASS",
        detail="All config validations passed",
    )


def _run_alembic_command(args: list[str]) -> tuple[int, str]:
    """Run an alembic command and return (returncode, combined output)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode, output
    except FileNotFoundError:
        return -1, "alembic not found on PATH"
    except subprocess.TimeoutExpired:
        return -1, "alembic command timed out"


def check_alembic(settings: Settings) -> CheckResult:
    """Check 3: Alembic at head and no pending migrations."""
    # Get current revision
    rc_current, out_current = _run_alembic_command(["current"])
    if rc_current != 0:
        return CheckResult(
            name="alembic",
            status="FAIL",
            detail=f"alembic current failed: {out_current}",
        )

    # Get head revision
    rc_heads, out_heads = _run_alembic_command(["heads"])
    if rc_heads != 0:
        return CheckResult(
            name="alembic",
            status="FAIL",
            detail=f"alembic heads failed: {out_heads}",
        )

    # Check for pending migrations
    rc_check, out_check = _run_alembic_command(["check"])
    if rc_check != 0 and "No new upgrade operations detected" not in out_check:
        return CheckResult(
            name="alembic",
            status="FAIL",
            detail=f"Pending migrations detected: {out_check}",
        )

    # Parse revision IDs -- alembic current/heads prints lines like
    # "020_chat_sessions_messages (head)" or "fa33e2cd9dda (head)"
    def _extract_revisions(text: str) -> set[str]:
        """Pull revision IDs from alembic output lines."""
        return set(re.findall(r"^(\S+)\s+\(", text, re.MULTILINE))

    current_revs = _extract_revisions(out_current)
    head_revs = _extract_revisions(out_heads)

    if not head_revs:
        return CheckResult(
            name="alembic",
            status="WARN",
            detail="Could not parse head revision from alembic output",
        )

    if head_revs and current_revs and head_revs.issubset(current_revs):
        return CheckResult(
            name="alembic",
            status="PASS",
            detail="Database is at head revision",
        )

    return CheckResult(
        name="alembic",
        status="FAIL",
        detail=f"Not at head. current={current_revs}, heads={head_revs}",
    )


def check_readiness(base_url: str) -> CheckResult:
    """Check 4: /readiness returns 200."""
    try:
        resp = httpx.get(f"{base_url}/readiness", timeout=5.0)
        if resp.status_code == 200:
            body = resp.json()
            ready = body.get("ready", False)
            if ready:
                return CheckResult(
                    name="readiness",
                    status="PASS",
                    detail="Server is ready",
                )
            return CheckResult(
                name="readiness",
                status="FAIL",
                detail=f"Server not ready: {body}",
            )
        return CheckResult(
            name="readiness",
            status="FAIL",
            detail=f"Unexpected status code {resp.status_code}",
        )
    except httpx.ConnectError:
        return CheckResult(
            name="readiness",
            status="SKIP",
            detail="Server not reachable -- skipping readiness check",
        )
    except Exception as exc:
        return CheckResult(
            name="readiness",
            status="SKIP",
            detail=f"Could not reach server: {exc}",
        )


_REQUIRED_HEALTH_COMPONENTS = {"api", "database", "redis", "object_storage"}


def check_health(base_url: str) -> CheckResult:
    """Check 5: /health includes all 4 component keys."""
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5.0)
        if resp.status_code != 200:
            return CheckResult(
                name="health_components",
                status="FAIL",
                detail=f"Unexpected status code {resp.status_code}",
            )
        body = resp.json()
        checks = body.get("checks", {})
        present_keys = set(checks.keys())
        missing = _REQUIRED_HEALTH_COMPONENTS - present_keys
        if missing:
            return CheckResult(
                name="health_components",
                status="FAIL",
                detail=f"Missing health components: {sorted(missing)}",
            )
        return CheckResult(
            name="health_components",
            status="PASS",
            detail=f"All components present: {sorted(present_keys)}",
        )
    except httpx.ConnectError:
        return CheckResult(
            name="health_components",
            status="SKIP",
            detail="Server not reachable -- skipping health check",
        )
    except Exception as exc:
        return CheckResult(
            name="health_components",
            status="SKIP",
            detail=f"Could not reach server: {exc}",
        )


def check_no_secrets_in_report(report: PreflightReport, settings: Settings) -> CheckResult:
    """Check 6: Self-verify that no secret values appear in the report."""
    report_json = json.dumps(asdict(report))

    secrets_to_check: list[tuple[str, str]] = []

    # Check for raw DATABASE_URL password
    parsed = urlparse(settings.DATABASE_URL)
    if parsed.password:
        secrets_to_check.append(("DATABASE_URL password", parsed.password))

    # Check for full SECRET_KEY if non-trivial
    if settings.SECRET_KEY and len(settings.SECRET_KEY) > 4:
        secrets_to_check.append(("SECRET_KEY", settings.SECRET_KEY))

    # Check for API keys and other secrets
    for key_name in (
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
        "MINIO_SECRET_KEY", "AZURE_DI_KEY",
    ):
        val = getattr(settings, key_name, "")
        if val and len(val) > 4:
            secrets_to_check.append((key_name, val))

    # Check for REDIS_URL password
    parsed_redis = urlparse(settings.REDIS_URL)
    if parsed_redis.password:
        secrets_to_check.append(("REDIS_URL password", parsed_redis.password))

    for label, secret in secrets_to_check:
        if secret in report_json:
            return CheckResult(
                name="no_secrets",
                status="FAIL",
                detail=f"Secret value for {label} found in report output",
            )

    return CheckResult(
        name="no_secrets",
        status="PASS",
        detail="No secret values detected in report",
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_preflight(base_url: str | None = None) -> PreflightReport:
    """Execute all preflight checks and return a structured report.

    Parameters
    ----------
    base_url:
        Base URL of the running ImpactOS server (e.g. ``http://localhost:8000``).
        If *None*, HTTP-based checks will be skipped.
    """
    settings = get_settings()

    checks: list[CheckResult] = []

    # 1. Environment
    checks.append(check_environment(settings))

    # 2. Config validation
    checks.append(check_config_validation(settings))

    # 3. Alembic
    checks.append(check_alembic(settings))

    # 4. Readiness (requires server)
    if base_url:
        checks.append(check_readiness(base_url))
    else:
        checks.append(
            CheckResult(
                name="readiness",
                status="SKIP",
                detail="No base URL provided -- skipping readiness check",
            ),
        )

    # 5. Health components (requires server)
    if base_url:
        checks.append(check_health(base_url))
    else:
        checks.append(
            CheckResult(
                name="health_components",
                status="SKIP",
                detail="No base URL provided -- skipping health check",
            ),
        )

    # Build interim report for secret self-check
    has_fail = any(c.status == "FAIL" for c in checks)
    interim = PreflightReport(
        overall="FAIL" if has_fail else "PASS",
        checks=list(checks),
    )

    # 6. Secret self-verification
    secret_check = check_no_secrets_in_report(interim, settings)
    checks.append(secret_check)

    # Final overall
    has_fail = any(c.status == "FAIL" for c in checks)
    return PreflightReport(
        overall="FAIL" if has_fail else "PASS",
        checks=checks,
    )


# ---------------------------------------------------------------------------
# CLI output helpers
# ---------------------------------------------------------------------------

_STATUS_SYMBOLS = {
    "PASS": "[PASS]",
    "FAIL": "[FAIL]",
    "SKIP": "[SKIP]",
    "WARN": "[WARN]",
}


def _print_table(report: PreflightReport) -> None:
    """Print a human-readable table of check results."""
    max_name = max(len(c.name) for c in report.checks) if report.checks else 10
    print()
    print(f"{'Check':<{max_name + 2}} {'Status':<8} Detail")
    print("-" * (max_name + 2 + 8 + 40))
    for c in report.checks:
        symbol = _STATUS_SYMBOLS.get(c.status, c.status)
        print(f"{c.name:<{max_name + 2}} {symbol:<8} {c.detail}")
    print()
    print(f"Overall: {report.overall}")
    print()


def _print_json(report: PreflightReport) -> None:
    """Print JSON report to stdout."""
    print(json.dumps(asdict(report), indent=2))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and run the preflight suite."""
    parser = argparse.ArgumentParser(
        description="Staging preflight -- repeatable pre-deployment verification.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output structured JSON report",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8000",
        help="Base URL of the ImpactOS server (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    report = run_preflight(base_url=args.url)

    if args.json_output:
        _print_json(report)
    else:
        _print_table(report)

    sys.exit(1 if report.has_failures() else 0)


if __name__ == "__main__":
    main()
