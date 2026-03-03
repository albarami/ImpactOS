"""Shared pytest fixtures for ImpactOS test suite.

Provides:
- db_engine: in-memory SQLite async engine with all tables
- db_session: SAVEPOINT-isolated async session (app commits don't leak)
- client: AsyncClient with dependency overrides for DB + auth (default principal)
"""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

import src.db.tables  # noqa: F401 — register ORM models on Base.metadata
from src.api.auth_deps import (
    AuthPrincipal,
    WorkspaceMember,
    get_current_principal,
    require_workspace_member,
)
from src.db.session import Base, get_async_session

_DEFAULT_PRINCIPAL = AuthPrincipal(
    user_id=UUID("00000000-0000-7000-8000-000000000001"),
    username="test-admin",
    role="admin",
)


@pytest.fixture
async def db_engine():
    """Create an in-memory SQLite async engine with all tables."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Provide a SAVEPOINT-isolated session.

    The outer transaction is never committed — it rolls back at teardown.
    Application code calling session.commit() triggers a SAVEPOINT release,
    which is then restarted so subsequent operations stay in the same
    outer transaction. This ensures full test isolation.
    """
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        nested = await conn.begin_nested()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(sync_session, transaction):  # noqa: ARG001
            nonlocal nested
            if transaction.nested and not transaction._parent.nested:
                nested = conn.sync_connection.begin_nested()

        yield session

        await session.close()
        await trans.rollback()


@pytest.fixture
async def client(db_session):
    """AsyncClient with session + auth overrides for non-auth tests.

    The auth dependency is overridden to return a default principal so
    that existing tests continue working without passing auth headers.
    Auth-specific tests use their own unauthed_client fixture instead.
    """
    from src.api.main import app

    async def _override_session():
        yield db_session

    async def _override_principal():
        return _DEFAULT_PRINCIPAL

    async def _override_workspace_member(workspace_id: UUID = None):
        return WorkspaceMember(
            principal=_DEFAULT_PRINCIPAL,
            workspace_id=workspace_id or UUID("00000000-0000-7000-8000-000000000010"),
            role="admin",
        )

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_current_principal] = _override_principal
    app.dependency_overrides[require_workspace_member] = _override_workspace_member

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
