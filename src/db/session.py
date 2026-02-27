"""SQLAlchemy async session setup for ImpactOS.

Provides:
- Base: DeclarativeBase for all ORM models
- engine: async engine configured from settings
- async_session_factory: session maker bound to engine
- get_async_session: FastAPI dependency with Unit-of-Work commit/rollback
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config.settings import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


_settings = get_settings()

engine = create_async_engine(
    _settings.DATABASE_URL,
    echo=(_settings.ENVIRONMENT == "dev"),
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session with Unit-of-Work semantics.

    Repositories only call add()/flush()/refresh().
    Commit happens once at the end of a successful request.
    Rollback happens on any exception.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
