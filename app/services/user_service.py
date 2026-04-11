"""
User service — profile management and skill list management.

Key responsibilities:
  - get / update user profiles
  - add / remove offered skills  (also updates Redis inverted indexes)
  - add / remove wanted  skills  (also updates Redis inverted indexes)

Redis sync:
  Every time a skill is added or removed we MUST update four Redis keys:
    user:{uid}:offered_skills  or  user:{uid}:wanted_skills
    skill:{sid}:offered_by     or  skill:{sid}:wanted_by
  AND invalidate the user's cached matches (they may have changed).
  This keeps the matching engine's fast-path data in sync with the DB.
"""

import json
import structlog
from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import RedisKeys
from app.models.skill import Skill
from app.models.user import User
from app.models.user_skill import UserSkillOffered, UserSkillWanted
from app.schemas.user import UserProfileUpdate
from app.schemas.user_skill import OfferedSkillCreate, WantedSkillCreate

logger = structlog.get_logger(__name__)


class UserService:

    # ── Profile ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get_profile(db: AsyncSession, user_id: str) -> User:
        """Load a user with all offered/wanted skills eagerly loaded."""
        result = await db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return user

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        redis: Redis,
        user: User,
        payload: UserProfileUpdate,
    ) -> User:
        """Apply partial profile updates. Only provided fields are changed."""
        updates = payload.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(user, field, value)
        db.add(user)
        # Invalidate cached profile
        await redis.delete(RedisKeys.user_profile(user.id))
        logger.info("profile_updated", user_id=user.id, fields=list(updates.keys()))
        return user

    # ── Offered Skills ────────────────────────────────────────────────────────

    @staticmethod
    async def add_offered_skill(
        db: AsyncSession,
        redis: Redis,
        user: User,
        payload: OfferedSkillCreate,
    ) -> UserSkillOffered:
        """
        Add a skill to the user's offered list.

        Steps:
          1. Verify the skill exists in the catalogue.
          2. Check for duplicates (UNIQUE constraint would catch it too, but
             a clear 409 is better UX than a DB IntegrityError).
          3. Insert the row.
          4. Update Redis: add skill to user's offered SET + skill's offered_by SET.
          5. Invalidate the user's match cache (new skill may create new matches).
        """
        # Step 1: Skill must exist
        skill = await db.get(Skill, payload.skill_id)
        if not skill or not skill.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{payload.skill_id}' not found.",
            )

        # Step 2: Duplicate check
        existing = await db.execute(
            select(UserSkillOffered).where(
                UserSkillOffered.user_id == user.id,
                UserSkillOffered.skill_id == payload.skill_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You already offer '{skill.name}'.",
            )

        # Step 3: Insert
        offered = UserSkillOffered(
            user_id=user.id,
            skill_id=payload.skill_id,
            proficiency_level=payload.proficiency_level,
            description=payload.description,
            years_experience=payload.years_experience,
        )
        db.add(offered)
        await db.flush()

        # Step 4: Sync Redis
        await redis.sadd(RedisKeys.user_offered_skills(user.id), payload.skill_id)
        await redis.sadd(RedisKeys.skill_offered_by(payload.skill_id), user.id)

        # Step 5: Invalidate match cache
        await redis.delete(RedisKeys.user_matches(user.id))

        logger.info("offered_skill_added", user_id=user.id, skill_id=payload.skill_id)
        return offered

    @staticmethod
    async def remove_offered_skill(
        db: AsyncSession,
        redis: Redis,
        user: User,
        offered_skill_id: str,
    ) -> None:
        """Remove an offered skill and clean up Redis indexes."""
        result = await db.execute(
            select(UserSkillOffered).where(
                UserSkillOffered.id == offered_skill_id,
                UserSkillOffered.user_id == user.id,
            )
        )
        offered = result.scalar_one_or_none()
        if not offered:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offered skill not found or does not belong to you.",
            )

        skill_id = offered.skill_id
        await db.delete(offered)

        # Sync Redis
        await redis.srem(RedisKeys.user_offered_skills(user.id), skill_id)
        await redis.srem(RedisKeys.skill_offered_by(skill_id), user.id)
        await redis.delete(RedisKeys.user_matches(user.id))

        logger.info("offered_skill_removed", user_id=user.id, skill_id=skill_id)

    # ── Wanted Skills ─────────────────────────────────────────────────────────

    @staticmethod
    async def add_wanted_skill(
        db: AsyncSession,
        redis: Redis,
        user: User,
        payload: WantedSkillCreate,
    ) -> UserSkillWanted:
        """Add a skill to the user's wanted list and update Redis."""
        skill = await db.get(Skill, payload.skill_id)
        if not skill or not skill.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{payload.skill_id}' not found.",
            )

        existing = await db.execute(
            select(UserSkillWanted).where(
                UserSkillWanted.user_id == user.id,
                UserSkillWanted.skill_id == payload.skill_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You already want to learn '{skill.name}'.",
            )

        wanted = UserSkillWanted(
            user_id=user.id,
            skill_id=payload.skill_id,
            urgency=payload.urgency,
            description=payload.description,
        )
        db.add(wanted)
        await db.flush()

        # Sync Redis
        await redis.sadd(RedisKeys.user_wanted_skills(user.id), payload.skill_id)
        await redis.sadd(RedisKeys.skill_wanted_by(payload.skill_id), user.id)
        await redis.delete(RedisKeys.user_matches(user.id))

        logger.info("wanted_skill_added", user_id=user.id, skill_id=payload.skill_id)
        return wanted

    @staticmethod
    async def remove_wanted_skill(
        db: AsyncSession,
        redis: Redis,
        user: User,
        wanted_skill_id: str,
    ) -> None:
        """Remove a wanted skill and clean up Redis indexes."""
        result = await db.execute(
            select(UserSkillWanted).where(
                UserSkillWanted.id == wanted_skill_id,
                UserSkillWanted.user_id == user.id,
            )
        )
        wanted = result.scalar_one_or_none()
        if not wanted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wanted skill not found or does not belong to you.",
            )

        skill_id = wanted.skill_id
        await db.delete(wanted)

        await redis.srem(RedisKeys.user_wanted_skills(user.id), skill_id)
        await redis.srem(RedisKeys.skill_wanted_by(skill_id), user.id)
        await redis.delete(RedisKeys.user_matches(user.id))

        logger.info("wanted_skill_removed", user_id=user.id, skill_id=skill_id)

    # ── Redis warm-up (called after registration / first login) ───────────────

    @staticmethod
    async def sync_redis_for_user(db: AsyncSession, redis: Redis, user_id: str) -> None:
        """
        Rebuild all Redis skill-set keys for a user from the DB.
        Called when a user logs in for the first time or when cache is cold.
        Ensures the matching engine always has accurate data.
        """
        offered_res = await db.execute(
            select(UserSkillOffered.skill_id).where(UserSkillOffered.user_id == user_id)
        )
        wanted_res = await db.execute(
            select(UserSkillWanted.skill_id).where(UserSkillWanted.user_id == user_id)
        )

        offered_ids = [r[0] for r in offered_res.fetchall()]
        wanted_ids = [r[0] for r in wanted_res.fetchall()]

        # Atomically rebuild the sets
        pipe = redis.pipeline()
        pipe.delete(RedisKeys.user_offered_skills(user_id))
        pipe.delete(RedisKeys.user_wanted_skills(user_id))
        if offered_ids:
            pipe.sadd(RedisKeys.user_offered_skills(user_id), *offered_ids)
            for sid in offered_ids:
                pipe.sadd(RedisKeys.skill_offered_by(sid), user_id)
        if wanted_ids:
            pipe.sadd(RedisKeys.user_wanted_skills(user_id), *wanted_ids)
            for sid in wanted_ids:
                pipe.sadd(RedisKeys.skill_wanted_by(sid), user_id)
        await pipe.execute()
