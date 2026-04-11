"""UserSkillOffered and UserSkillWanted request/response schemas."""

from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user_skill import ProficiencyLevel, UrgencyLevel
from app.schemas.skill import SkillPublic


# ── Offered ───────────────────────────────────────────────────────────────────

class OfferedSkillCreate(BaseModel):
    """
    POST /users/me/offered  request body.

    Example:
        {
          "skill_id": "3fa85f64-...",
          "proficiency_level": "expert",
          "description": "3 years Django, 5 deployed projects",
          "years_experience": 3.0
        }
    """

    skill_id: str = Field(..., description="UUID of an existing skill")
    proficiency_level: ProficiencyLevel = Field(
        default=ProficiencyLevel.INTERMEDIATE
    )
    description: Optional[str] = Field(None, max_length=500)
    years_experience: Optional[float] = Field(None, ge=0, le=50)

    model_config = {"json_schema_extra": {
        "example": {
            "skill_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "proficiency_level": "expert",
            "description": "3 years Django, 5 deployed projects",
            "years_experience": 3.0,
        }
    }}


class OfferedSkillPublic(BaseModel):
    """Outbound representation of an offered skill (nested in UserProfile)."""

    id: str
    skill: SkillPublic
    proficiency_level: ProficiencyLevel
    description: Optional[str]
    years_experience: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Wanted ────────────────────────────────────────────────────────────────────

class WantedSkillCreate(BaseModel):
    """
    POST /users/me/wanted  request body.

    Example:
        {
          "skill_id": "3fa85f64-...",
          "urgency": "high",
          "description": "Need React for my final-year project"
        }
    """

    skill_id: str = Field(..., description="UUID of an existing skill")
    urgency: UrgencyLevel = Field(default=UrgencyLevel.MEDIUM)
    description: Optional[str] = Field(None, max_length=500)

    model_config = {"json_schema_extra": {
        "example": {
            "skill_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "urgency": "high",
            "description": "Need React for my final-year project",
        }
    }}


class WantedSkillPublic(BaseModel):
    """Outbound representation of a wanted skill (nested in UserProfile)."""

    id: str
    skill: SkillPublic
    urgency: UrgencyLevel
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
