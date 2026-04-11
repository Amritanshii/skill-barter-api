"""
Users router — /api/v1/users/*

Endpoints:
  GET    /me/profile           → full profile with skills
  PATCH  /me/profile           → update profile fields
  GET    /me/offered           → list offered skills
  POST   /me/offered           → add offered skill
  DELETE /me/offered/{id}      → remove offered skill
  GET    /me/wanted            → list wanted skills
  POST   /me/wanted            → add wanted skill
  DELETE /me/wanted/{id}       → remove wanted skill
  GET    /{username}           → view any user's public profile
"""

from fastapi import APIRouter, status

from app.dependencies import CurrentUser, DBSession, RedisClient
from app.schemas.user import UserProfile, UserProfileUpdate, UserPublic
from app.schemas.user_skill import (
    OfferedSkillCreate,
    OfferedSkillPublic,
    WantedSkillCreate,
    WantedSkillPublic,
)
from app.services.user_service import UserService
from sqlalchemy import select

router = APIRouter()


# ── My Profile ────────────────────────────────────────────────────────────────

@router.get(
    "/me/profile",
    response_model=UserProfile,
    summary="Get my full profile (with skills)",
)
async def get_my_profile(current_user: CurrentUser, db: DBSession):
    """
    Returns the authenticated user's full profile including:
    - All offered skills with proficiency level and description
    - All wanted skills with urgency level and description
    """
    user = await UserService.get_profile(db, current_user.id)
    return UserProfile.model_validate(user)


@router.patch(
    "/me/profile",
    response_model=UserPublic,
    summary="Update my profile",
)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
):
    """
    Partially update profile fields. Only include fields you want to change.

    Request body (all optional):
        {
          "full_name": "Alice Smith",
          "college": "MIT",
          "bio": "CS junior, love building things",
          "avatar_url": "https://..."
        }
    """
    user = await UserService.update_profile(db, redis, current_user, payload)
    return UserPublic.model_validate(user)


# ── Offered Skills ────────────────────────────────────────────────────────────

@router.get(
    "/me/offered",
    response_model=list[OfferedSkillPublic],
    summary="List my offered skills",
)
async def list_offered_skills(current_user: CurrentUser, db: DBSession):
    """Returns all skills I currently offer."""
    user = await UserService.get_profile(db, current_user.id)
    return [OfferedSkillPublic.model_validate(s) for s in user.offered_skills]


@router.post(
    "/me/offered",
    response_model=OfferedSkillPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Add a skill I offer",
)
async def add_offered_skill(
    payload: OfferedSkillCreate,
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
):
    """
    Add a skill to my offered list.

    This also updates Redis immediately so the matching engine reflects
    the change on the next match query without waiting for cache expiry.

    Request body:
        {
          "skill_id": "3fa85f64-...",
          "proficiency_level": "expert",
          "description": "3 years Django, 5 deployed projects",
          "years_experience": 3.0
        }
    """
    offered = await UserService.add_offered_skill(db, redis, current_user, payload)
    # Reload with skill relationship populated
    from sqlalchemy.orm import selectinload
    from app.models.user_skill import UserSkillOffered
    result = await db.execute(
        select(UserSkillOffered)
        .where(UserSkillOffered.id == offered.id)
        .options(selectinload(UserSkillOffered.skill))
    )
    offered_loaded = result.scalar_one()
    return OfferedSkillPublic.model_validate(offered_loaded)


@router.delete(
    "/me/offered/{offered_skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a skill I offer",
)
async def remove_offered_skill(
    offered_skill_id: str,
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
):
    """
    Remove an offered skill by its record ID (not the skill_id, but the
    user_skills_offered.id). Redis indexes are updated immediately.
    """
    await UserService.remove_offered_skill(db, redis, current_user, offered_skill_id)
    return None


# ── Wanted Skills ─────────────────────────────────────────────────────────────

@router.get(
    "/me/wanted",
    response_model=list[WantedSkillPublic],
    summary="List skills I want to learn",
)
async def list_wanted_skills(current_user: CurrentUser, db: DBSession):
    """Returns all skills I currently want to learn."""
    user = await UserService.get_profile(db, current_user.id)
    return [WantedSkillPublic.model_validate(s) for s in user.wanted_skills]


@router.post(
    "/me/wanted",
    response_model=WantedSkillPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Add a skill I want to learn",
)
async def add_wanted_skill(
    payload: WantedSkillCreate,
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
):
    """
    Add a skill to my wanted list.

    Request body:
        {
          "skill_id": "3fa85f64-...",
          "urgency": "high",
          "description": "Need React for my final-year project"
        }
    """
    wanted = await UserService.add_wanted_skill(db, redis, current_user, payload)
    from sqlalchemy.orm import selectinload
    from app.models.user_skill import UserSkillWanted
    result = await db.execute(
        select(UserSkillWanted)
        .where(UserSkillWanted.id == wanted.id)
        .options(selectinload(UserSkillWanted.skill))
    )
    wanted_loaded = result.scalar_one()
    return WantedSkillPublic.model_validate(wanted_loaded)


@router.delete(
    "/me/wanted/{wanted_skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a skill I want to learn",
)
async def remove_wanted_skill(
    wanted_skill_id: str,
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
):
    """Remove a wanted skill. Redis indexes are updated immediately."""
    await UserService.remove_wanted_skill(db, redis, current_user, wanted_skill_id)
    return None


# ── Public Profile ────────────────────────────────────────────────────────────

@router.get(
    "/{username}",
    response_model=UserProfile,
    summary="View any user's public profile",
)
async def get_user_profile(
    username: str,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    View any user's public profile by username.
    Returns their full profile including offered and wanted skills.
    Requires authentication (you must be logged in to browse profiles).
    """
    from app.models.user import User
    result = await db.execute(
        select(User).where(User.username == username, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    return UserProfile.model_validate(user)
