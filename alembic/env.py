"""
Alembic migration environment.

Why this file matters:
  Alembic needs to know:
  1. Where your models are (so autogenerate can diff them against the DB)
  2. The DB connection URL (sync driver — alembic doesn't support asyncpg)
  3. Whether to run in online mode (connect to live DB) or offline mode
     (generate SQL scripts without connecting)

Async setup:
  SQLAlchemy 2.x with asyncpg requires a special async runner for Alembic.
  We use run_async_migrations() wrapped in asyncio.run() so Alembic's sync
  CLI can drive async migrations.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

# Ensure the project root is on sys.path so `from app.xxx import ...` works
# whether alembic is run from inside Docker (/app) or locally.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# ── Import all models so Alembic can detect them ─────────────────────────────
# This is critical: if a model isn't imported here, autogenerate won't see it.
from app.models.base import Base
from app.models import User, Skill, UserSkillOffered, UserSkillWanted, Match  # noqa: F401

# Load app config to get the DB URL
from app.config import get_settings

settings = get_settings()

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config

# Override the sqlalchemy.url from alembic.ini with our app's sync URL
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata: Alembic diffs this against the actual DB schema
target_metadata = Base.metadata


# ── Offline Mode ──────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations without connecting to the database.
    Generates SQL scripts that can be reviewed and applied manually.
    Useful for production deployments where direct DB access is restricted.

    Usage: alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,          # detect column type changes
        compare_server_default=True, # detect default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online Mode (Async) ───────────────────────────────────────────────────────

def do_run_migrations(connection: Connection) -> None:
    """Configure and run migrations on an existing connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Include schemas if you use PostgreSQL schemas
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations.
    We use NullPool because Alembic creates/drops the engine after each run —
    persistent pools are wasted here.

    We create the engine directly with the asyncpg URL (settings.DATABASE_URL)
    rather than reading from alembic.ini, because alembic.ini holds the psycopg2
    sync URL (used only for offline SQL generation) and async_engine_from_config
    would try to import psycopg2, which is not installed.
    """
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (connected) migrations."""
    asyncio.run(run_async_migrations())


# ── Entry Point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
