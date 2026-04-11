"""
Skills router — /api/v1/skills/*

Endpoints:
  GET  /          → paginated list with optional category + search filter
  POST /          → create a new skill in the catalogue
  GET  /autocomplete → fast name prefix search (for UI skill picker)
  GET  /{skill_id} → get a single skill by ID
"""

from fastapi import APIRouter, Query, status

from app.dependencies import CurrentUser, DBSession, RedisClient
from app.schemas.skill import SkillCreate, SkillPublic
from app.services.skill_service import SkillService

router = APIRouter()


@router.get(
    "",
    response_model=dict,
    summary="List all skills (paginated)",
)
async def list_skills(
    db: DBSession,
    redis: RedisClient,
    current_user: CurrentUser,
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Name prefix search, e.g. 'Py'"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
):
    """
    List skills from the catalogue.

    Query params:
      - category: programming | design | music | languages | mathematics |
                  writing | marketing | finance | science | arts | sports | other
      - search:   autocomplete-style prefix, e.g. ?search=Py → Python, PyGame…
      - page, limit: pagination

    Response:
        {
          "items": [ ...SkillPublic... ],
          "total": 142,
          "page": 1,
          "limit": 50,
          "pages": 3
        }
    """
    skills, total = await SkillService.list_skills(db, redis, category, search, page, limit)
    import math
    return {
        "items": [SkillPublic.model_validate(s) for s in skills],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if total else 0,
    }


@router.get(
    "/autocomplete",
    response_model=list[SkillPublic],
    summary="Autocomplete skill names (for skill picker UI)",
)
async def autocomplete_skills(
    db: DBSession,
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Prefix to search for"),
    limit: int = Query(10, ge=1, le=20),
):
    """
    Returns up to 10 skills whose names start with `q`.
    Designed for frontend autocomplete dropdowns.
    Fast O(log n) query due to index on skill.name.

    Example: GET /skills/autocomplete?q=Py
      → [{"name": "Python", ...}, {"name": "PyGame", ...}]
    """
    skills = await SkillService.search_skills(db, q, limit)
    return [SkillPublic.model_validate(s) for s in skills]


@router.post(
    "",
    response_model=SkillPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new skill to the catalogue",
)
async def create_skill(
    payload: SkillCreate,
    db: DBSession,
    redis: RedisClient,
    current_user: CurrentUser,
):
    """
    Add a new skill to the global catalogue.
    Any authenticated user can suggest a skill.
    Duplicate names (case-insensitive) return 409.

    Request body:
        {
          "name": "Rust",
          "category": "programming",
          "description": "Systems programming language"
        }
    """
    skill = await SkillService.create_skill(db, redis, payload)
    return SkillPublic.model_validate(skill)


@router.get(
    "/{skill_id}",
    response_model=SkillPublic,
    summary="Get a single skill by ID",
)
async def get_skill(
    skill_id: str,
    db: DBSession,
    current_user: CurrentUser,
):
    """Fetch details of a specific skill by its UUID."""
    skill = await SkillService.get_skill(db, skill_id)
    return SkillPublic.model_validate(skill)
