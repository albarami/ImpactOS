"""Tests for S11-2: External IdP RS256/JWKS validation for non-dev.

Covers: non-dev rejects HS256 self-signed tokens, RS256 with valid
issuer/audience/key succeeds, bad issuer/audience/signature → 401,
missing JWKS_URL in non-dev → fail-closed 401.

Uses monkeypatch to override ENVIRONMENT to staging for non-dev tests.
"""

from unittest.mock import patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session


def _generate_rsa_keypair():
    """Generate an RSA key pair for test RS256 tokens."""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048,
    )
    public_key = private_key.public_key()
    return private_key, public_key


def _create_rs256_token(
    private_key, *, sub: str, username: str, role: str,
    issuer: str, audience: str,
) -> str:
    payload = {
        "sub": sub,
        "username": username,
        "role": role,
        "iss": issuer,
        "aud": audience,
    }
    return pyjwt.encode(payload, private_key, algorithm="RS256")


@pytest.fixture
async def unauthed_client(db_session: AsyncSession) -> AsyncClient:
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ===================================================================
# S11-2: Non-dev rejects HS256 self-signed dev tokens
# ===================================================================


class TestNonDevRejectsDevTokens:

    @pytest.mark.anyio
    async def test_hs256_dev_token_rejected_in_staging(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        """Staging env must reject HS256 self-signed dev tokens."""
        from src.config import settings as settings_mod

        original = settings_mod.get_settings

        def _staging_settings():
            s = original()
            object.__setattr__(s, "ENVIRONMENT", "staging")
            object.__setattr__(s, "JWKS_URL", "")
            return s

        monkeypatch.setattr(settings_mod, "get_settings", _staging_settings)
        monkeypatch.setattr(
            "src.api.auth_deps.get_settings", _staging_settings,
        )

        dev_token = pyjwt.encode(
            {"sub": "test", "username": "a", "role": "admin"},
            "dev-secret-change-in-production",
            algorithm="HS256",
        )
        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": f"Bearer {dev_token}"},
        )
        assert resp.status_code == 401


# ===================================================================
# S11-2: RS256 with valid issuer/audience/key succeeds
# ===================================================================


class TestRS256Validation:

    @pytest.mark.anyio
    async def test_valid_rs256_token_accepted(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        """Valid RS256 token with correct issuer/audience passes auth."""
        private_key, public_key = _generate_rsa_keypair()
        from src.config import settings as settings_mod

        original = settings_mod.get_settings

        def _staging_settings():
            s = original()
            object.__setattr__(s, "ENVIRONMENT", "staging")
            object.__setattr__(s, "JWT_ISSUER", "https://idp.example.com")
            object.__setattr__(s, "JWT_AUDIENCE", "impactos-api")
            object.__setattr__(
                s, "JWKS_URL", "https://idp.example.com/.well-known/jwks",
            )
            return s

        monkeypatch.setattr(settings_mod, "get_settings", _staging_settings)
        monkeypatch.setattr(
            "src.api.auth_deps.get_settings", _staging_settings,
        )

        token = _create_rs256_token(
            private_key,
            sub="00000000-0000-7000-8000-000000000001",
            username="analyst", role="analyst",
            issuer="https://idp.example.com",
            audience="impactos-api",
        )

        pem_bytes = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        with patch(
            "src.api.auth_deps._fetch_jwks_public_key",
            return_value=pem_bytes,
        ):
            resp = await unauthed_client.get(
                "/v1/workspaces",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200


# ===================================================================
# S11-2: Bad issuer/audience/signature → 401
# ===================================================================


class TestRS256Rejection:

    @pytest.mark.anyio
    async def test_wrong_issuer_rejected(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        private_key, public_key = _generate_rsa_keypair()
        from src.config import settings as settings_mod

        original = settings_mod.get_settings

        def _staging_settings():
            s = original()
            object.__setattr__(s, "ENVIRONMENT", "staging")
            object.__setattr__(s, "JWT_ISSUER", "https://idp.example.com")
            object.__setattr__(s, "JWT_AUDIENCE", "impactos-api")
            object.__setattr__(
                s, "JWKS_URL", "https://idp.example.com/.well-known/jwks",
            )
            return s

        monkeypatch.setattr(settings_mod, "get_settings", _staging_settings)
        monkeypatch.setattr(
            "src.api.auth_deps.get_settings", _staging_settings,
        )

        token = _create_rs256_token(
            private_key,
            sub="00000000-0000-7000-8000-000000000001",
            username="a", role="admin",
            issuer="https://evil.com",
            audience="impactos-api",
        )

        pem_bytes = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        with patch(
            "src.api.auth_deps._fetch_jwks_public_key",
            return_value=pem_bytes,
        ):
            resp = await unauthed_client.get(
                "/v1/workspaces",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_wrong_audience_rejected(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        private_key, public_key = _generate_rsa_keypair()
        from src.config import settings as settings_mod

        original = settings_mod.get_settings

        def _staging_settings():
            s = original()
            object.__setattr__(s, "ENVIRONMENT", "staging")
            object.__setattr__(s, "JWT_ISSUER", "https://idp.example.com")
            object.__setattr__(s, "JWT_AUDIENCE", "impactos-api")
            object.__setattr__(
                s, "JWKS_URL", "https://idp.example.com/.well-known/jwks",
            )
            return s

        monkeypatch.setattr(settings_mod, "get_settings", _staging_settings)
        monkeypatch.setattr(
            "src.api.auth_deps.get_settings", _staging_settings,
        )

        token = _create_rs256_token(
            private_key,
            sub="00000000-0000-7000-8000-000000000001",
            username="a", role="admin",
            issuer="https://idp.example.com",
            audience="wrong-audience",
        )

        pem_bytes = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        with patch(
            "src.api.auth_deps._fetch_jwks_public_key",
            return_value=pem_bytes,
        ):
            resp = await unauthed_client.get(
                "/v1/workspaces",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_wrong_signature_rejected(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        """Token signed with wrong key is rejected."""
        private_key, _ = _generate_rsa_keypair()
        _, wrong_public = _generate_rsa_keypair()
        from src.config import settings as settings_mod

        original = settings_mod.get_settings

        def _staging_settings():
            s = original()
            object.__setattr__(s, "ENVIRONMENT", "staging")
            object.__setattr__(s, "JWT_ISSUER", "https://idp.example.com")
            object.__setattr__(s, "JWT_AUDIENCE", "impactos-api")
            object.__setattr__(
                s, "JWKS_URL", "https://idp.example.com/.well-known/jwks",
            )
            return s

        monkeypatch.setattr(settings_mod, "get_settings", _staging_settings)
        monkeypatch.setattr(
            "src.api.auth_deps.get_settings", _staging_settings,
        )

        token = _create_rs256_token(
            private_key,
            sub="00000000-0000-7000-8000-000000000001",
            username="a", role="admin",
            issuer="https://idp.example.com",
            audience="impactos-api",
        )

        wrong_pem = wrong_public.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        with patch(
            "src.api.auth_deps._fetch_jwks_public_key",
            return_value=wrong_pem,
        ):
            resp = await unauthed_client.get(
                "/v1/workspaces",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 401
