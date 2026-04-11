"""
Application configuration loaded from environment variables / .env file.

Why pydantic-settings?
- Reads from .env automatically — no manual os.getenv() calls scattered everywhere.
- All config values are type-validated at startup; bad config = immediate crash
  with a clear error, not a mysterious failure 10 minutes into runtime.
- Singleton pattern via @lru_cache means the .env file is parsed exactly once.

Usage anywhere in the app:
    from app.config import get_settings
    settings = get_settings()
    print(settings.DATABASE_URL)
"""

from functools import lru_cache
from typing import List

from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration class.
    All values are read from environment variables (or .env file).
    Pydantic validates and coerces types automatically.
    """

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_NAME: str = "Skill Barter API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str
    # Separate sync URL for Alembic (asyncpg doesn't work with Alembic's sync runner)
    # Derived automatically — no need to set manually
    POSTGRES_USER: str = "skillbarter"
    POSTGRES_PASSWORD: str = "skillbarter_dev_password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "skillbarter_db"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # ── Cache TTLs ────────────────────────────────────────────────────────────
    MATCH_CACHE_TTL: int = 300        # seconds
    PROFILE_CACHE_TTL: int = 600
    SKILL_LIST_CACHE_TTL: int = 3600

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # ── Server ────────────────────────────────────────────────────────────────
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    WORKERS: int = 1

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS_ORIGINS into a Python list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def sync_database_url(self) -> str:
        """
        Return a synchronous (psycopg2-compatible) DB URL for Alembic.
        Alembic's migration runner is synchronous; it can't use asyncpg.
        We swap the driver prefix: postgresql+asyncpg → postgresql+psycopg2
        """
        return self.DATABASE_URL.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        ).replace(
            "postgresql://", "postgresql+psycopg2://"
        )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                "Generate one with: openssl rand -hex 32"
            )
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def database_url_must_use_async_driver(cls, v: str) -> str:
        """
        Enforce that DATABASE_URL uses asyncpg driver.
        Mixing sync and async drivers causes subtle connection pool bugs.
        """
        if not (v.startswith("postgresql+asyncpg://") or v.startswith("postgresql://")):
            raise ValueError(
                "DATABASE_URL must start with 'postgresql+asyncpg://' "
                "or 'postgresql://' (asyncpg will be inferred)"
            )
        # Normalise: ensure asyncpg prefix
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # ── Model config ──────────────────────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",           # load from .env file if present
        env_file_encoding="utf-8",
        case_sensitive=True,       # env vars are UPPER_CASE
        extra="ignore",            # silently ignore unknown env vars
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    @lru_cache ensures .env is parsed exactly once across the app lifetime.
    FastAPI dependency injection usage:

        from fastapi import Depends
        from app.config import get_settings, Settings

        @router.get("/health")
        async def health(settings: Settings = Depends(get_settings)):
            return {"version": settings.APP_VERSION}
    """
    return Settings()
