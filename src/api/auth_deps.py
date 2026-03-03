"""Shared auth dependencies for Sprint 10 — authN/authZ rollout.

Provides:
- AuthPrincipal: typed identity extracted from JWT claims
- get_current_principal: FastAPI dependency for token validation (401)
- require_workspace_member: workspace membership check (404)
- require_role: role policy gate factory (403)

Secret safety: tokens and signing keys are never logged.
Dev stub compatibility: _DEV_USERS lookup used only when ENVIRONMENT=dev.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import jwt
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


def _extract_bearer_token(request: Request) -> str:
    """Extract Bearer token from Authorization header.

    Raises HTTPException(401) if header is missing or malformed.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return token


def _validate_jwt(token: str) -> dict:
    """Decode and validate a JWT token.

    Raises HTTPException(401) on invalid/expired/malformed token.
    Never logs the raw token value.
    """
    settings = get_settings()
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_principal(request: Request) -> AuthPrincipal:
    """Extract and validate JWT bearer token into an AuthPrincipal.

    Raises HTTPException(401) for missing, invalid, or expired tokens.
    The role claim comes from the JWT payload.
    """
    token = _extract_bearer_token(request)

    settings = get_settings()
    if settings.ENVIRONMENT == "dev":
        from src.api.auth import _revoked_tokens
        if token in _revoked_tokens:
            raise HTTPException(status_code=401, detail="Token revoked")

    claims = _validate_jwt(token)

    user_id_str = claims.get("sub")
    username = claims.get("username", "")
    role = claims.get("role", "viewer")

    if not user_id_str:
        raise HTTPException(status_code=401, detail="Invalid token claims")

    return AuthPrincipal(
        user_id=UUID(user_id_str),
        username=username,
        role=role,
    )


async def require_workspace_member(
    workspace_id: UUID,
    principal: AuthPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkspaceMember:
    """Verify the authenticated principal is a member of the workspace.

    Raises HTTPException(404) if not a member — fail-closed, no data
    leakage about workspace existence.
    """
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
        raise HTTPException(status_code=404, detail="Workspace not found")

    _logger.info(
        "Auth allow: user=%s workspace=%s role=%s",
        principal.user_id, workspace_id, membership.role,
    )

    return WorkspaceMember(
        principal=principal,
        workspace_id=workspace_id,
        role=membership.role,
    )


def require_role(*allowed_roles: str):
    """Dependency factory: gate access by workspace membership role.

    Returns a FastAPI dependency that checks the member's workspace role
    against the allowed set. Raises HTTPException(403) if not permitted.

    Usage::

        @router.put("/{workspace_id}/...")
        async def update_thing(
            member: WorkspaceMember = Depends(require_role("manager", "admin")),
        ):
            ...
    """

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
