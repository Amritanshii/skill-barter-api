"""
Skill model — the canonical catalogue of skills on the platform.

Design decisions:
- Normalised as a separate table so skills are reusable across many users;
  prevents 1000 users each spelling "JavaScript" differently.
- 'name' is UNIQUE + indexed for dedup checks and fast autocomplete queries.
- 'category' has an index because the most common filter is
  "show me skills in the 'programming' category".
- Skills are immutable once created (no soft-delete): removing a skill would
  orphan user_skills_offered/wanted rows. Use is_active if you need that.
"""

from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user_skill import UserSkillOffered, UserSkillWanted


# Allowed categories — enforced at the service/schema layer, not DB level,
# so adding a new category is a code change only, not a migration.
SKILL_CATEGORIES = [
    "programming",
    "design",
    "music",
    "languages",
    "mathematics",
    "writing",
    "marketing",
    "finance",
    "science",
    "arts",
    "sports",
    "other",
]


class Skill(Base, TimestampMixin):
    """
    Represents a single learnable / teachable skill.

    Examples: "Python", "Guitar", "Spanish", "Photoshop", "Calculus"

    Relationships:
      offered_by  → UserSkillOffered (users who offer this skill)
      wanted_by   → UserSkillWanted  (users who want this skill)
    """

    __tablename__ = "skills"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
    )

    # ── Core fields ───────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Title-cased, e.g. 'Python', 'Adobe Photoshop'",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment=f"One of: {', '.join(SKILL_CATEGORIES)}",
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Short explanation of what this skill covers",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Inactive skills are hidden from UI but kept for data integrity",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    offered_by: Mapped[List["UserSkillOffered"]] = relationship(
        "UserSkillOffered",
        back_populates="skill",
        lazy="selectin",
    )
    wanted_by: Mapped[List["UserSkillWanted"]] = relationship(
        "UserSkillWanted",
        back_populates="skill",
        lazy="selectin",
    )

    # ── Composite Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        # Partial index: only index active skills — reduces index size
        Index(
            "ix_skills_name_active",
            "name",
            postgresql_where=(
                # raw text clause — SQLAlchemy accepts strings here
                "is_active = TRUE"
            ),
        ),
    )

    def __repr__(self) -> str:
        return f"<Skill id={self.id} name={self.name!r} category={self.category!r}>"
