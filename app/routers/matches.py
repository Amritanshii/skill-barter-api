"""
Matches router — /api/v1/matches/*

Endpoints:
  GET    /           → list my matches sorted by score (cache-first)
  GET    /{id}       → get a single match detail
  PATCH  /{id}       → accept / reject / complete a match
  DELETE /{id}/cache → force-refresh my match cache (admin/debug)
"""

from fastapi import APIRouter, Query, status

from app.dependencies import CurrentUser, DBSession, RedisClient
from app.models.match import MatchStatus
from app.schemas.match import MatchPublic, MatchStatusUpdate
from app.services.match_service import MatchService

router = APIRouter()


@router.get(
    "",
    response_model=dict,
    summary="Get my skill-exchange matches",
)
async def get_my_matches(
    current_user: CurrentUser,
    db: DBSession,
    redis: RedisClient,
    refresh: bool = Query(False, description="Force bypass cache and recompute"),
    limit: int = Query(20, ge=1, le=50),
):
    """
    Returns a list of users who are bidirectional skill matches for the
    authenticated user — sorted by match score descending.

    Response (from cache if warm, computed otherwise):
        {
          "matches": [
            {
              "other_user_id": "...",
              "other_username": "bob_designs",
              "other_college": "Stanford",
              "skill_i_offer_name": "Python",
              "skill_they_offer_name": "Figma",
              "match_score": 0.75
            },
            ...
          ],
          "total": 5,
          "cached": true
        }

    Performance:
      - Cache HIT  (Redis): ~2ms
      - Cache MISS (SQL):  ~60ms → repopulates cache
    """
    from app.core.redis_client import RedisKeys
    import json

    # Check if result came from cache
    cache_key = RedisKeys.user_matches(current_user.id)
    was_cached = not refresh and bool(await redis.get(cache_key))

    matches = await MatchService.get_matches(db, redis, current_user, force_refresh=refresh)

    return {
        "matches": matches[:limit],
        "total": len(matches),
        "cached": was_cached,
    }


@router.get(
    "/{match_id}",
    response_model=dict,
    summary="Get a specific match by ID",
)
async def get_match(
    match_id: str,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Fetch detailed information about a specific match.
    Only the two participants may view their match.

    Response:
        {
          "id": "...",
          "status": "pending",
          "match_score": 0.75,
          "user_a": { ...UserPublic... },
          "user_b": { ...UserPublic... },
          "skill_offered_by_a": { ...SkillPublic... },
          "skill_offered_by_b": { ...SkillPublic... },
          "created_at": "..."
        }
    """
    match = await MatchService.get_match_by_id(db, match_id, current_user.id)

    from app.models.user import User
    from app.models.skill import Skill
    from sqlalchemy import select

    user_a = await db.get(User, match.user_a_id)
    user_b = await db.get(User, match.user_b_id)
    skill_a = await db.get(Skill, match.skill_offered_by_a)
    skill_b = await db.get(Skill, match.skill_offered_by_b)

    from app.schemas.user import UserPublic
    from app.schemas.skill import SkillPublic

    return {
        "id": match.id,
        "status": match.status,
        "match_score": match.match_score,
        "user_a": UserPublic.model_validate(user_a),
        "user_b": UserPublic.model_validate(user_b),
        "skill_offered_by_a": SkillPublic.model_validate(skill_a),
        "skill_offered_by_b": SkillPublic.model_validate(skill_b),
        "initiated_by": match.initiated_by,
        "created_at": match.created_at.isoformat(),
        "updated_at": match.updated_at.isoformat(),
    }


@router.patch(
    "/{match_id}",
    response_model=dict,
    summary="Accept, reject, or complete a match",
)
async def update_match_status(
    match_id: str,
    payload: MatchStatusUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Update the lifecycle status of a match.

    Valid transitions:
      pending   → accepted   (you want to connect)
      pending   → rejected   (not interested)
      accepted  → completed  (exchange happened, mark done)

    Request body:
        { "status": "accepted" }

    Only the two matched users may update their own match.
    """
    match = await MatchService.update_match_status(
        db, match_id, current_user.id, payload.status
    )
    return {
        "id": match.id,
        "status": match.status,
        "match_score": match.match_score,
        "message": f"Match status updated to '{match.status}'.",
    }


@router.delete(
    "/cache",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate my match cache (force recompute on next GET)",
)
async def invalidate_match_cache(
    current_user: CurrentUser,
    redis: RedisClient,
):
    """
    Bust the cached match results for the current user.
    Next call to GET /matches will recompute from scratch.
    Useful after bulk skill changes.
    """
    from app.core.redis_client import RedisKeys
    await redis.delete(RedisKeys.user_matches(current_user.id))
    return None
