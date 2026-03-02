"""B-13: Auth contract (dev stub).

Dev-only authentication for frontend development.
Returns 404 in staging/prod environments.
Gets replaced by SSO in production.
"""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.config.settings import get_settings

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# Stable UUIDs for dev users — must match frontend dev auth stub
_DEV_USERS: dict[str, dict[str, str | list[str]]] = {
    "analyst": {
        "user_id": "00000000-0000-7000-8000-000000000001",
        "username": "analyst",
        "role": "analyst",
        "workspace_ids": ["00000000-0000-7000-8000-000000000010"],
    },
    "manager": {
        "user_id": "00000000-0000-7000-8000-000000000002",
        "username": "manager",
        "role": "manager",
        "workspace_ids": ["00000000-0000-7000-8000-000000000010"],
    },
    "admin": {
        "user_id": "00000000-0000-7000-8000-000000000003",
        "username": "admin",
        "role": "admin",
        "workspace_ids": [
            "00000000-0000-7000-8000-000000000010",
            "00000000-0000-7000-8000-000000000020",
        ],
    },
}

# In-memory token denylist (dev stub only — acceptable per spec)
_revoked_tokens: set[str] = set()


class LoginRequest(BaseModel):
    """Credentials for dev login."""

    username: str
    password: str


class AuthResponse(BaseModel):
    """Successful login response with JWT token."""

    token: str
    user_id: str
    username: str
    role: str
    workspace_ids: list[str]


class MeResponse(BaseModel):
    """Current user profile response."""

    user_id: str
    username: str
    role: str
    workspace_ids: list[str]


def _check_dev_mode() -> None:
    """Raise 404 if not running in dev environment."""
    settings = get_settings()
    if settings.ENVIRONMENT != "dev":
        raise HTTPException(status_code=404)


def _create_token(user_id: str, username: str) -> str:
    """Create a JWT token for the given user."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "username": username,
        "exp": datetime.now(UTC) + timedelta(hours=24),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _decode_token(token: str) -> dict[str, str]:
    """Decode and validate a JWT token."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def _extract_token(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return auth[7:]


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest) -> AuthResponse:
    """Authenticate a dev user and return a JWT token."""
    _check_dev_mode()
    user = _DEV_USERS.get(body.username)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    token = _create_token(str(user["user_id"]), str(user["username"]))
    return AuthResponse(
        token=token,
        user_id=str(user["user_id"]),
        username=str(user["username"]),
        role=str(user["role"]),
        workspace_ids=list(user["workspace_ids"]),
    )


@router.get("/me", response_model=MeResponse)
async def me(request: Request) -> MeResponse:
    """Return the current user profile from the JWT token."""
    _check_dev_mode()
    token = _extract_token(request)
    if token in _revoked_tokens:
        raise HTTPException(status_code=401, detail="Token revoked")
    payload = _decode_token(token)
    username = payload.get("username", "")
    user = _DEV_USERS.get(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return MeResponse(
        user_id=str(user["user_id"]),
        username=str(user["username"]),
        role=str(user["role"]),
        workspace_ids=list(user["workspace_ids"]),
    )


@router.post("/logout")
async def logout(request: Request) -> dict[str, str]:
    """Revoke the current token by adding it to the denylist."""
    _check_dev_mode()
    token = _extract_token(request)
    _revoked_tokens.add(token)
    return {"status": "logged_out"}
