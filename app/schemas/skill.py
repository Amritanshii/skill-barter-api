"""Skill catalogue schemas."""

from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.skill import SKILL_CATEGORIES


class SkillCreate(BaseModel):
    """POST /skills  request body."""

    name: str = Field(..., min_length=2, max_length=100)
    category: str = Field(..., description=f"One of: {', '.join(SKILL_CATEGORIES)}")
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def title_case_name(cls, v: str) -> str:
        return v.strip().title()

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in SKILL_CATEGORIES:
            raise ValueError(
                f"category must be one of: {', '.join(SKILL_CATEGORIES)}"
            )
        return v

    model_config = {"json_schema_extra": {
        "example": {"name": "Python", "category": "programming",
                    "description": "General-purpose programming language"}
    }}


class SkillPublic(BaseModel):
    """Outbound skill representation."""

    id: str
    name: str
    category: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
