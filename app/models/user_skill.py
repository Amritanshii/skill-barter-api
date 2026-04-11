"""
UserSkillOffered and UserSkillWanted — the join tables that link users to skills.

These are NOT simple many-to-many association tables. Each row carries extra
columns (proficiency level, description, urgency) that make them proper
first-class entities deserving their own model classes.

Design decisions:
- UNIQUE(user_id, skill_id) on both tables — a user can't offer/want the same
  skill twice.
- skill_id is separately indexed so the matching engine can run:
    "SELECT user_id FROM user_skills_offered WHERE skill_id = :sid"
  in O(log n) time — this is the HOT PATH of the entire matching algorithm.
- Python Enum for proficiency / urgency keeps values controlled without needing
  a separate lookup table.
"""

import enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.skill import Skill


# ── Enums ─────────────────────────────────────────────────────────────────────

class ProficiencyLevel(str, enum.Enum):
    """
    How good is the user at a skill they OFFER?
    Storing as str enum means the value in the DB is the readable string,
    not an integer — easier to debug and Alembic-safe.
    """
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT       = "expert"


class UrgencyLevel(str, enum.Enum):
    """How urgently does the user WANT to learn this skill?"""
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ── UserSkillOffered ──────────────────────────────────────────────────────────

class UserSkillOffered(Base, TimestampMixin):
    """
    Records that a User offers a particular Skill.

    Key queries this table supports:
    1. "What skills does user X offer?"
       → SELECT * FROM user_skills_offered WHERE user_id = :uid   [ix_uso_user]
    2. "Who offers skill Y?" (matching hot path)
       → SELECT user_id FROM user_skills_offered WHERE skill_id = :sid [ix_uso_skill]
    """

    __tablename__ = "user_skills_offered"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
    )

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owner of this offered-skill entry",
    )
    skill_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The skill being offered",
    )

    # ── Extra Columns ─────────────────────────────────────────────────────────
    proficiency_level: Mapped[ProficiencyLevel] = mapped_column(
        SAEnum(ProficiencyLevel, name="proficiency_level_enum"),
        nullable=False,
        default=ProficiencyLevel.INTERMEDIATE,
        comment="Self-assessed proficiency; used in match scoring",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Free-text blurb, e.g. '3 years Django, built 5 projects'",
    )
    years_experience: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Optional numeric experience indicator",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User",
        back_populates="offered_skills",
        lazy="selectin",
    )
    skill: Mapped["Skill"] = relationship(
        "Skill",
        back_populates="offered_by",
        lazy="selectin",
    )

    # ── Constraints & Indexes ─────────────────────────────────────────────────
    __table_args__ = (
        # A user cannot offer the same skill twice
        UniqueConstraint("user_id", "skill_id", name="uq_offered_user_skill"),
        # Index on user_id  → "show me all skills user X offers"
        Index("ix_uso_user_id", "user_id"),
        # Index on skill_id → "who offers skill Y?" (matching hot path)
        Index("ix_uso_skill_id", "skill_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserSkillOffered user={self.user_id} skill={self.skill_id} "
            f"level={self.proficiency_level}>"
        )


# ── UserSkillWanted ───────────────────────────────────────────────────────────

class UserSkillWanted(Base, TimestampMixin):
    """
    Records that a User wants to learn a particular Skill.

    Key queries this table supports:
    1. "What skills does user X want?"
       → SELECT * FROM user_skills_wanted WHERE user_id = :uid   [ix_usw_user]
    2. "Who wants skill Y?" (matching hot path)
       → SELECT user_id FROM user_skills_wanted WHERE skill_id = :sid [ix_usw_skill]
    """

    __tablename__ = "user_skills_wanted"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
    )

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ── Extra Columns ─────────────────────────────────────────────────────────
    urgency: Mapped[UrgencyLevel] = mapped_column(
        SAEnum(UrgencyLevel, name="urgency_level_enum"),
        nullable=False,
        default=UrgencyLevel.MEDIUM,
        comment="How urgently this skill is needed; boosts match score for HIGH",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Free-text, e.g. 'Need React for my final year project'",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User",
        back_populates="wanted_skills",
        lazy="selectin",
    )
    skill: Mapped["Skill"] = relationship(
        "Skill",
        back_populates="wanted_by",
        lazy="selectin",
    )

    # ── Constraints & Indexes ─────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_wanted_user_skill"),
        Index("ix_usw_user_id", "user_id"),
        # This index is the MOST critical in the whole schema:
        # every match query does a lookup here by skill_id
        Index("ix_usw_skill_id", "skill_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserSkillWanted user={self.user_id} skill={self.skill_id} "
            f"urgency={self.urgency}>"
        )
