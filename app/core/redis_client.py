"""
Redis connection management and high-level cache helpers.

Why a wrapper module instead of using redis-py directly everywhere?
  - Single connection pool shared across the app (no per-request overhead).
  - Centralised key naming: all keys are defined here, so a typo in one
    place doesn't create orphaned cache entries.
  - Easy to mock in tests: replace get_redis() with a fake client.
  - hiredis parser (C extension) is 5-10× faster than the pure-Python parser.

Connection pool:
  decode_responses=True means Redis returns Python str instead of bytes.
  max_connections=20 matches our DB pool size — balanced resource usage.
"""

from typing import AsyncGenerator, Optional

import redis.asyncio as aioredis
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

# ── Singleton pool ────────────────────────────────────────────────────────────

_redis_pool: Optional[aioredis.ConnectionPool] = None


def _get_pool() -> aioredis.ConnectionPool:
    """Build (or return cached) connection pool."""
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=20,
            decode_responses=True,       # auto-decode bytes → str
        )
    return _redis_pool


def get_redis_client() -> aioredis.Redis:
    """
    Return an async Redis client backed by the shared connection pool.
    Called at module import time by dependencies.py.
    """
    return aioredis.Redis(connection_pool=_get_pool())


async def close_redis_pool() -> None:
    """Called on app shutdown — gracefully close the pool."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("redis_pool_closed")


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """
    FastAPI dependency that provides the Redis client per request.
    No per-request connection setup — just returns the pool-backed client.

    Usage in a router:
        from redis.asyncio import Redis
        from app.core.redis_client import get_redis

        @router.get("/matches")
        async def get_matches(redis: Redis = Depends(get_redis)):
            cached = await redis.get(f"user:{uid}:matches")
    """
    client = get_redis_client()
    try:
        yield client
    finally:
        # Connection returns to pool automatically — no explicit close needed
        pass


# ── Health check ──────────────────────────────────────────────────────────────

async def check_redis_connection() -> bool:
    """Ping Redis — used by GET /health."""
    try:
        client = get_redis_client()
        await client.ping()
        return True
    except Exception as exc:
        logger.error("redis_health_check_failed", error=str(exc))
        return False


# ── Key builders ─────────────────────────────────────────────────────────────
# Central place for all Redis key patterns.
# This prevents key typos and makes it easy to find what keys exist.

class RedisKeys:
    """
    Namespace for all Redis key patterns used in this application.
    All keys use colon-separated namespacing (Redis convention).

    Usage:
        key = RedisKeys.user_matches(user_id)
        await redis.get(key)
    """

    # ── User skill sets (used by matching engine) ─────────────────────────
    @staticmethod
    def user_offered_skills(user_id: str) -> str:
        """SET of skill IDs this user offers."""
        return f"user:{user_id}:offered_skills"

    @staticmethod
    def user_wanted_skills(user_id: str) -> str:
        """SET of skill IDs this user wants."""
        return f"user:{user_id}:wanted_skills"

    # ── Inverted indexes ──────────────────────────────────────────────────
    @staticmethod
    def skill_offered_by(skill_id: str) -> str:
        """SET of user IDs who offer this skill."""
        return f"skill:{skill_id}:offered_by"

    @staticmethod
    def skill_wanted_by(skill_id: str) -> str:
        """SET of user IDs who want this skill."""
        return f"skill:{skill_id}:wanted_by"

    # ── Cached results ────────────────────────────────────────────────────
    @staticmethod
    def user_matches(user_id: str) -> str:
        """JSON string: cached match results for this user."""
        return f"user:{user_id}:matches"

    @staticmethod
    def user_profile(user_id: str) -> str:
        """JSON string: cached user profile."""
        return f"user:{user_id}:profile"

    @staticmethod
    def skill_list() -> str:
        """JSON string: cached full skill catalogue."""
        return "skills:catalogue"

    # ── Auth ──────────────────────────────────────────────────────────────
    @staticmethod
    def blacklisted_token(jti: str) -> str:
        """Key exists = token is blacklisted (logged out)."""
        return f"blacklist:token:{jti}"

    # ── Rate limiting ─────────────────────────────────────────────────────
    @staticmethod
    def rate_limit(user_id: str, endpoint: str) -> str:
        """Counter key for sliding-window rate limiting."""
        return f"ratelimit:{user_id}:{endpoint}"

    # ── Matching engine temp keys ─────────────────────────────────────────
    @staticmethod
    def tmp_candidates(user_id: str) -> str:
        """Temp SET: users who offer what user X wants."""
        return f"tmp:{user_id}:candidates"

    @staticmethod
    def tmp_want_what_i_offer(user_id: str) -> str:
        """Temp SET: users who want what user X offers."""
        return f"tmp:{user_id}:want_what_i_offer"
