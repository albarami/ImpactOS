"""Shared auth dependencies — Sprint 10+11 authN/authZ + IdP hardening.

Provides:
- AuthPrincipal: typed identity extracted from JWT claims
- get_current_principal: FastAPI dependency for token validation (401)
  - dev: HS256 with SECRET_KEY (dev stub only)
  - non-dev: RS256 with external IdP JWKS + issuer/audience validation
- require_workspace_member: workspace membership check (404)
- require_role: workspace role policy gate factory (403)
- require_global_role: global (non-workspace) role gate factory (403)

Secret safety: tokens and signing keys are never logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.db.session import get_async_session
from src.db.tables import WorkspaceMembershipRow

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthPrincipal:
    """Authenticated identity extracted from JWT claims."""

    user_id: UUID
    username: str
    role: str


@dataclass(frozen=True)
class WorkspaceMember:
    """Principal verified as a member of a specific workspace."""

    principal: AuthPrincipal
    workspace_id: UUID
    role: str


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------


def _extract_bearer_token(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid token",
        )
    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(
            status_code=401, detail="Missing or invalid token",
        )
    return token


# ---------------------------------------------------------------------------
# Dev-mode HS256 validation
# ---------------------------------------------------------------------------


def _validate_jwt_dev(token: str) -> dict[str, Any]:
    """Decode HS256 JWT using SECRET_KEY. Dev environment only."""
    settings = get_settings()
    try:
        return pyjwt.decode(
            token, settings.SECRET_KEY, algorithms=["HS256"],
        )
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=401, detail="Invalid or expired token",
        )


# ---------------------------------------------------------------------------
# Non-dev RS256/JWKS validation
# ---------------------------------------------------------------------------


def _fetch_jwks_public_key(jwks_url: str) -> bytes:
    """Fetch the first RSA public key from a JWKS endpoint.

    In production this would cache keys and handle rotation.
    Never logs the key material itself.
    """
    import httpx

    resp = httpx.get(jwks_url, timeout=10)
    resp.raise_for_status()
    jwks = resp.json()

    from cryptography.hazmat.primitives import serialization
    from jwt.algorithms import RSAAlgorithm

    for key_data in jwks.get("keys", []):
        if key_data.get("kty") == "RSA":
            public_key = RSAAlgorithm.from_jwk(key_data)
            return public_key.public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )

    raise HTTPException(
        status_code=401, detail="No suitable RSA key in JWKS",
    )


def _validate_jwt_external(token: str) -> dict[str, Any]:
    """Decode RS256 JWT using external IdP JWKS + issuer/audience.

    Fail-closed: missing JWKS_URL, JWT_ISSUER, or JWT_AUDIENCE → 401.
    All three are mandatory in non-dev environments.
    """
    settings = get_settings()

    missing = []
    if not settings.JWKS_URL:
        missing.append("JWKS_URL")
    if not settings.JWT_ISSUER:
        missing.append("JWT_ISSUER")
    if not settings.JWT_AUDIENCE:
        missing.append("JWT_AUDIENCE")

    if missing:
        _logger.error(
            "IdP auth not configured: missing %s", ", ".join(missing),
        )
        raise HTTPException(
            status_code=401,
            detail="Auth not configured for this environment",
        )

    try:
        public_key_pem = _fetch_jwks_public_key(settings.JWKS_URL)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("Failed to fetch JWKS")
        raise HTTPException(
            status_code=401, detail="Auth service unavailable",
        )

    try:
        return pyjwt.decode(
            token,
            public_key_pem,
            algorithms=["RS256"],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=401, detail="Invalid or expired token",
        )


# ---------------------------------------------------------------------------
# Principal dependency
# ---------------------------------------------------------------------------


async def get_current_principal(request: Request) -> AuthPrincipal:
    """Extract and validate JWT bearer token into an AuthPrincipal.

    Dev: HS256 with SECRET_KEY + revocation check.
    Non-dev: RS256 with external IdP JWKS + issuer/audience.
    """
    token = _extract_bearer_token(request)
    settings = get_settings()

    if settings.ENVIRONMENT == "dev":
        from src.api.auth import _revoked_tokens

        if token in _revoked_tokens:
            raise HTTPException(
                status_code=401, detail="Token revoked",
            )
        claims = _validate_jwt_dev(token)
    else:
        claims = _validate_jwt_external(token)

    user_id_str = claims.get("sub")
    username = claims.get("username", "")
    role = claims.get("role", "viewer")

    if not user_id_str:
        raise HTTPException(
            status_code=401, detail="Invalid token claims",
        )

    return AuthPrincipal(
        user_id=UUID(user_id_str),
        username=username,
        role=role,
    )


# ---------------------------------------------------------------------------
# Workspace membership dependency
# ---------------------------------------------------------------------------


async def require_workspace_member(
    workspace_id: UUID,
    principal: AuthPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkspaceMember:
    """Verify the principal is a workspace member. 404 if not."""
    from sqlalchemy import select

    stmt = select(WorkspaceMembershipRow).where(
        WorkspaceMembershipRow.workspace_id == workspace_id,
        WorkspaceMembershipRow.user_id == principal.user_id,
    )
    result = await session.execute(stmt)
    membership = result.scalar_one_or_none()

    if membership is None:
        _logger.info(
            "Auth deny: user=%s workspace=%s reason=not_member",
            principal.user_id, workspace_id,
        )
        raise HTTPException(
            status_code=404, detail="Workspace not found",
        )

    _logger.info(
        "Auth allow: user=%s workspace=%s role=%s",
        principal.user_id, workspace_id, membership.role,
    )

    return WorkspaceMember(
        principal=principal,
        workspace_id=workspace_id,
        role=membership.role,
    )


# ---------------------------------------------------------------------------
# Role gate factories
# ---------------------------------------------------------------------------


def require_role(*allowed_roles: str):
    """Workspace-scoped role gate. 403 if member role not in allowed set."""

    async def _check_role(
        member: WorkspaceMember = Depends(require_workspace_member),
    ) -> WorkspaceMember:
        if member.role not in allowed_roles:
            _logger.info(
                "Auth deny: user=%s workspace=%s role=%s "
                "required=%s reason=insufficient_role",
                member.principal.user_id,
                member.workspace_id,
                member.role,
                allowed_roles,
            )
            raise HTTPException(
                status_code=403, detail="Insufficient permissions",
            )
        return member

    return _check_role


def require_global_role(*allowed_roles: str):
    """Global (non-workspace) role gate. 403 if principal role not allowed."""

    async def _check_global_role(
        principal: AuthPrincipal = Depends(get_current_principal),
    ) -> AuthPrincipal:
        if principal.role not in allowed_roles:
            _logger.info(
                "Auth deny: user=%s role=%s required=%s "
                "reason=insufficient_global_role",
                principal.user_id,
                principal.role,
                allowed_roles,
            )
            raise HTTPException(
                status_code=403, detail="Insufficient permissions",
            )
        return principal

    return _check_global_role
