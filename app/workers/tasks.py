"""
Celery background tasks.

Task catalogue:
  recompute_matches_for_user  → triggered after skill add/remove
  warm_match_cache            → periodic: pre-warm cache for recently active users
  cleanup_expired_matches     → daily cron: expire stale pending matches
  rebuild_all_redis_indexes   → one-time: backfill Redis from DB (e.g. after Redis flush)

Why Celery for matching?
  Match recomputation involves DB joins + Redis writes. Doing it synchronously
  inside the HTTP request adds ~100ms latency on skill updates. Offloading to
  Celery makes the API respond instantly (<5ms) and the recomputation happens
  asynchronously in the background.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task
from celery.utils.log import get_task_logger

from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Task 1: Recompute matches for a single user ───────────────────────────────

@celery_app.task(
    name="tasks.recompute_matches_for_user",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def recompute_matches_for_user(self, user_id: str) -> dict:
    """
    Recompute and cache matches for a specific user.

    Triggered by: UserService.add_offered_skill / remove_offered_skill /
                  add_wanted_skill / remove_wanted_skill

    Flow:
      1. Load user from DB
      2. Run SQL matching engine (slow path)
      3. Rebuild Redis indexes for this user
      4. Cache new match results (5-min TTL)

    Returns a summary dict for Flower monitoring.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.core.redis_client import get_redis_client
        from app.models.user import User
        from app.services.match_service import MatchService
        from sqlalchemy import select

        redis = get_redis_client()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.id == user_id, User.is_active == True)
            )
            user = result.scalar_one_or_none()
            if not user:
                logger.warning(f"recompute_matches: user {user_id} not found, skipping")
                return {"status": "skipped", "reason": "user_not_found"}

            matches = await MatchService.get_matches(db, redis, user, force_refresh=True)
            logger.info(f"recompute_matches: user={user_id} found {len(matches)} matches")
            return {"status": "ok", "user_id": user_id, "match_count": len(matches)}

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error(f"recompute_matches failed for {user_id}: {exc}")
        raise self.retry(exc=exc)


# ── Task 2: Warm cache for recently active users ──────────────────────────────

@celery_app.task(
    name="tasks.warm_match_cache",
    bind=True,
)
def warm_match_cache(self) -> dict:
    """
    Periodic task: pre-warm match cache for users active in the last 24 hours.

    Schedule: every 10 minutes (configured in celery_app.py beat schedule)

    Why: After the 5-min TTL expires, the next request pays the SQL cost.
    Pre-warming ensures active users almost always hit the fast path.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.core.redis_client import get_redis_client, RedisKeys
        from app.models.user import User
        from app.services.match_service import MatchService
        from sqlalchemy import select

        redis = get_redis_client()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        warmed = 0

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User)
                .where(User.is_active == True, User.updated_at >= since)
                .limit(200)
            )
            users = result.scalars().all()

            for user in users:
                cache_key = RedisKeys.user_matches(user.id)
                if not await redis.exists(cache_key):
                    try:
                        await MatchService.get_matches(db, redis, user, force_refresh=False)
                        warmed += 1
                    except Exception as exc:
                        logger.warning(f"warm_cache failed for {user.id}: {exc}")

        logger.info(f"warm_match_cache: warmed {warmed}/{len(users)} users")
        return {"status": "ok", "warmed": warmed, "checked": len(users)}

    return _run_async(_run())


# ── Task 3: Cleanup stale pending matches ─────────────────────────────────────

@celery_app.task(
    name="tasks.cleanup_expired_matches",
    bind=True,
)
def cleanup_expired_matches(self) -> dict:
    """
    Daily task: mark pending matches older than 30 days as rejected.

    Rationale: A match that neither user has responded to in 30 days is stale.
    Keeping them as pending pollutes the match feed with irrelevant old entries.

    Schedule: daily at 02:00 UTC (configured in celery beat schedule)
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.models.match import Match, MatchStatus
        from sqlalchemy import select, update

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Match)
                .where(
                    Match.status == MatchStatus.PENDING,
                    Match.created_at < cutoff,
                )
                .values(status=MatchStatus.REJECTED)
            )
            await db.commit()
            expired_count = result.rowcount
            logger.info(f"cleanup_expired_matches: expired {expired_count} stale matches")
            return {"status": "ok", "expired": expired_count}

    return _run_async(_run())


# ── Task 4: Rebuild all Redis indexes from DB (recovery task) ─────────────────

@celery_app.task(
    name="tasks.rebuild_all_redis_indexes",
    bind=True,
    time_limit=300,  # 5 minute hard limit
)
def rebuild_all_redis_indexes(self) -> dict:
    """
    One-time recovery task: rebuild all Redis skill indexes from PostgreSQL.

    When to run:
      - After a Redis FLUSHALL (cache wipe)
      - After a Redis restart with no persistence
      - As a health check / consistency repair

    Run manually via: celery call tasks.rebuild_all_redis_indexes
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.core.redis_client import get_redis_client
        from app.services.user_service import UserService
        from app.models.user import User
        from sqlalchemy import select

        redis = get_redis_client()
        rebuilt = 0

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User.id).where(User.is_active == True)
            )
            user_ids = [r[0] for r in result.fetchall()]

            for user_id in user_ids:
                try:
                    await UserService.sync_redis_for_user(db, redis, user_id)
                    rebuilt += 1
                except Exception as exc:
                    logger.warning(f"rebuild_redis failed for {user_id}: {exc}")

        logger.info(f"rebuild_all_redis_indexes: rebuilt {rebuilt} users")
        return {"status": "ok", "rebuilt": rebuilt}

    return _run_async(_run())
