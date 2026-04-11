"""Match request/response schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.match import MatchStatus
from app.schemas.user import UserPublic
from app.schemas.skill import SkillPublic


class MatchPublic(BaseModel):
    """
    Outbound match representation.
    Returned by GET /matches and GET /matches/{id}.

    Example response:
        {
          "id": "abc123...",
          "match_score": 0.85,
          "status": "pending",
          "other_user": { ...UserPublic... },
          "i_offer": { ...SkillPublic... },
          "they_offer": { ...SkillPublic... },
          "created_at": "2024-01-15T10:30:00Z"
        }
    """

    id: str
    match_score: float = Field(..., description="0.0 – 1.0 bilateral overlap score")
    status: MatchStatus
    other_user: UserPublic = Field(
        ..., description="The matched user (not the one making the request)"
    )
    i_offer: SkillPublic = Field(
        ..., description="The skill I offer that they want"
    )
    they_offer: SkillPublic = Field(
        ..., description="The skill they offer that I want"
    )
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchStatusUpdate(BaseModel):
    """
    PATCH /matches/{id}  request body.
    Used to accept, reject, or complete a match.

    Example:
        { "status": "accepted" }
    """

    status: MatchStatus = Field(
        ...,
        description="New status. allowed transitions: pending→accepted, pending→rejected, accepted→completed",
    )

    model_config = {"json_schema_extra": {"example": {"status": "accepted"}}}
