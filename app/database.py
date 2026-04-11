"""
Async database engine and session factory.

Architecture:
  - Uses SQLAlchemy 2.x async engine with asyncpg driver.
  - AsyncSessionLocal is a session factory used by FastAPI's DI system.
  - get_db() is the standard FastAPI dependency that yields one session
    per request and rolls back + closes on any exception.

Why async?
  A synchronous DB call blocks the entire event loop thread. With async,
  FastAPI can handle other requests while waiting for PostgreSQL I/O.
  At 100 concurrent users each making a 50ms DB query:
    Sync:  100 × 50ms = 5000ms total blocked time
    Async: ~50ms total (all queries run concurrently)

Connection pool settings (production-tuned):
  pool_size=10      : maintain 10 persistent connections
  max_overflow=20   : allow up to 20 extra connections under burst load
  pool_pre_ping=True: test connections before use (handles DB restarts)
  pool_recycle=3600 : recycle connections hourly (avoids stale TCP issues)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings

logger = structlog.get_logger(__name__)


def _build_engine(test_mode: bool = False) -> AsyncEngine:
    """
    Build the SQLAlchemy async engine.

    test_mode=True uses NullPool (no connection reuse) which is required
    for pytest-asyncio — each test gets a fresh connection.
    """
    settings = get_settings()

    engine_kwargs = {
        "url": settings.DATABASE_URL,
        "echo": settings.DEBUG,          # logs all SQL when DEBUG=true
        "pool_pre_ping": True,           # verify connections before use
    }

    if test_mode:
        # NullPool: each call to connect() opens a fresh connection.
        # Required for tests that use transactions for rollback isolation.
        engine_kwargs["poolclass"] = NullPool
    else:
        engine_kwargs.update({
            "pool_size": 10,
            "max_overflow": 20,
            "pool_recycle": 3600,        # seconds — avoids stale TCP connections
            "pool_timeout": 30,          # wait up to 30s for a connection
        })

    return create_async_engine(**engine_kwargs)


# ── Module-level singletons ───────────────────────────────────────────────────

engine: AsyncEngine = _build_engine()

# async_sessionmaker is the v2-recommended factory
# expire_on_commit=False: objects remain accessible after session.commit()
# without needing an extra SELECT — important for returning objects in APIs
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,       # don't flush automatically; we control this explicitly
    autocommit=False,
)


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides one AsyncSession per request.

    Usage in a router:
        from fastapi import Depends
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.database import get_db

        @router.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()

    The 'async with' block:
      - Opens a session at the start of the request
      - yields it to the endpoint function
      - On success: commits and closes
      - On exception: rolls back and closes (prevents dirty state leaking
        across requests — critical in long-lived connection pools)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("db_session_error", error=str(exc))
            raise
        finally:
            await session.close()


# ── Health check helper ───────────────────────────────────────────────────────

async def check_db_connection() -> bool:
    """
    Verify PostgreSQL is reachable. Used by GET /health.
    Returns True on success, False on any connection error.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("db_health_check_failed", error=str(exc))
        return False


# ── Startup / Shutdown ────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Called on application startup.
    Does NOT create tables (Alembic does that); just verifies connectivity.
    """
    logger.info("db_connecting", url=get_settings().DATABASE_URL.split("@")[-1])
    healthy = await check_db_connection()
    if not healthy:
        raise RuntimeError("Cannot connect to PostgreSQL on startup.")
    logger.info("db_connected")


async def close_db() -> None:
    """Called on application shutdown — disposes the connection pool."""
    await engine.dispose()
    logger.info("db_pool_closed")
