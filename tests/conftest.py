"""
Pytest configuration and shared fixtures.

Strategy:
  - Each test gets its own DB transaction, rolled back at the end.
    This means tests never touch each other's data and the DB stays clean.
  - We use a real PostgreSQL test database (set TEST_DATABASE_URL in .env).
    SQLite is NOT used — it doesn't support the PostgreSQL-specific types we use.
  - Redis is mocked with fakeredis so tests don't need a running Redis instance.
  - The HTTPX AsyncClient is used as the test HTTP client (FastAPI recommends this).

Run tests:
    pytest -v                          # all tests
    pytest tests/test_auth.py -v       # single file
    pytest -v --cov=app --cov-report=term-missing  # with coverage
"""

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.database import get_db
from app.core.redis_client import get_redis
from app.main import create_app
from app.models.base import Base
from app.models import User, Skill, UserSkillOffered, UserSkillWanted, Match  # ensure all models are imported

settings = get_settings()

# ── Event loop ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Test database engine ──────────────────────────────────────────────────────

TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "/skillbarter_db", "/skillbarter_test"
)

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """
    Create the test database schema once per session.
    NullPool prevents connection reuse between tests.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a DB session that is ROLLED BACK after each test.
    Tests can write data freely without polluting the DB.
    """
    session_factory = async_sessionmaker(
        bind=test_engine, class_=AsyncSession,
        expire_on_commit=False, autoflush=False,
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ── Fake Redis ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def redis():
    """
    In-memory fake Redis instance per test.
    fakeredis supports all commands used by the app (SADD, SINTER, SUNIONSTORE, etc.)
    """
    async with FakeRedis() as fake_redis:
        yield fake_redis


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db, redis) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX async client wired to the FastAPI app with DI overrides:
      - get_db  → our rollback-safe test session
      - get_redis → our in-memory FakeRedis
    """
    app = create_app()

    async def override_get_db():
        yield db

    async def override_get_redis():
        yield redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ── Helper fixtures ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db: AsyncSession):
    """A plain (unauthenticated) user in the DB."""
    from app.core.security import hash_password
    user = User(
        email="testuser@mit.edu",
        username="testuser",
        hashed_password=hash_password("TestPass1"),
        full_name="Test User",
        college="MIT",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def test_user_b(db: AsyncSession):
    """A second user for bidirectional match testing."""
    from app.core.security import hash_password
    user = User(
        email="bob@stanford.edu",
        username="bob_dev",
        hashed_password=hash_password("TestPass1"),
        full_name="Bob Dev",
        college="Stanford",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user):
    """
    Perform a real login and return Authorization headers.
    Used by protected endpoint tests.
    """
    resp = await client.post("/api/v1/auth/login", json={
        "identifier": "testuser@mit.edu",
        "password": "TestPass1",
    })
    assert resp.status_code == 200
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def python_skill(db: AsyncSession):
    """A Python skill in the catalogue."""
    skill = Skill(name="Python", category="programming", description="Python language")
    db.add(skill)
    await db.flush()
    return skill


@pytest_asyncio.fixture
async def react_skill(db: AsyncSession):
    """A React skill in the catalogue."""
    skill = Skill(name="React", category="programming", description="React framework")
    db.add(skill)
    await db.flush()
    return skill
