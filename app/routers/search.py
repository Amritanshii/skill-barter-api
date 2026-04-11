"""
Search router — /api/v1/search/*

Endpoints:
  GET /users  → search users by skill name and/or college
"""

import structlog
from fastapi import APIRouter, Query
from sqlalchemy import and_, distinct, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DBSession
from app.models.skill import Skill
from app.models.user import User
from app.models.user_skill import UserSkillOffered
from app.schemas.user import UserProfile

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get(
    "/users",
    response_model=dict,
    summary="Search users by skill and/or college",
)
async def search_users(
    db: DBSession,
    current_user: CurrentUser,
    skill: str | None = Query(None, description="Skill name to search for (partial match)"),
    college: str | None = Query(None, description="College name (partial match)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    """
    Search for users by the skills they offer and/or their college.

    Query params:
      - skill:   partial name match on the skill they offer, e.g. ?skill=python
      - college: partial match on college name, e.g. ?college=MIT
      - page, limit: pagination

    Both filters can be combined: ?skill=python&college=MIT

    Response:
        {
          "items": [ ...UserProfile... ],
          "total": 12,
          "page": 1,
          "limit": 20,
          "pages": 1
        }

    Design:
      - JOIN users → user_skills_offered → skills for the skill filter
      - ILIKE for case-insensitive partial matching
      - Excludes the currently authenticated user from results
      - O(log n) thanks to indexes on skill.name and user.college
    """
    import math
    offset = (page - 1) * limit

    base_query = (
        select(User)
        .where(User.is_active == True, User.id != current_user.id)
    )

    if skill:
        # Join through offered skills → skills table, filter by name
        base_query = (
            base_query
            .join(UserSkillOffered, UserSkillOffered.user_id == User.id)
            .join(Skill, Skill.id == UserSkillOffered.skill_id)
            .where(Skill.name.ilike(f"%{skill}%"))
            .distinct()
        )

    if college:
        base_query = base_query.where(User.college.ilike(f"%{college}%"))

    # Count total before pagination
    from sqlalchemy import func
    count_query = select(func.count(distinct(User.id))).select_from(
        base_query.subquery()
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    # Apply pagination + eager load skills
    page_query = (
        base_query
        .order_by(User.username)
        .offset(offset)
        .limit(limit)
        .options(
            selectinload(User.offered_skills).selectinload(UserSkillOffered.skill),
        )
    )

    result = await db.execute(page_query)
    users = result.scalars().unique().all()

    logger.info(
        "users_searched",
        skill=skill,
        college=college,
        results=len(users),
        searcher=current_user.id,
    )

    return {
        "items": [UserProfile.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if total else 0,
    }


@router.get(
    "/skills",
    response_model=dict,
    summary="Search skills by name (for autocomplete)",
)
async def search_skills(
    db: DBSession,
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(10, ge=1, le=30),
):
    """
    Fast skill name search. Used by frontend skill-picker autocomplete.
    Returns skills whose name contains the query string.

    Example: GET /search/skills?q=java
      → Java, JavaScript, JavaFX
    """
    result = await db.execute(
        select(Skill)
        .where(Skill.is_active == True, Skill.name.ilike(f"%{q}%"))
        .order_by(Skill.name)
        .limit(limit)
    )
    skills = result.scalars().all()

    from app.schemas.skill import SkillPublic
    return {
        "items": [SkillPublic.model_validate(s) for s in skills],
        "total": len(skills),
    }
