"""
User model.

Design decisions:
- UUID primary key: avoids enumeration attacks (attacker can't guess user IDs).
- email + username each have UNIQUE constraints + btree indexes so login and
  profile lookups are O(log n) rather than full table scans.
- hashed_password stores the bcrypt hash ONLY — never the raw password.
- is_active flag allows soft-deleting accounts without cascading deletes.
- is_verified can be toggled by an email verification flow (future scope).
"""

from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user_skill import UserSkillOffered, UserSkillWanted
    from app.models.match import Match


class User(Base, TimestampMixin):
    """
    Represents a college student on the platform.

    Relationships:
      offered_skills  → UserSkillOffered (one-to-many)
      wanted_skills   → UserSkillWanted  (one-to-many)
      matches_as_a    → Match (as user_a, one-to-many)
      matches_as_b    → Match (as user_b, one-to-many)
    """

    __tablename__ = "users"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        comment="UUID v4 — avoids sequential ID enumeration",
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,          # btree index → fast login lookups
        comment="Must be a college .edu address (validated at service layer)",
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-safe, lowercase username shown on profile",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt hash with cost factor 12",
    )

    # ── Profile ───────────────────────────────────────────────────────────────
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    college: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,          # allows filtering matches by college
    )
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="False = soft-deleted; excluded from all match queries",
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True once email verification is complete",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    offered_skills: Mapped[List["UserSkillOffered"]] = relationship(
        "UserSkillOffered",
        back_populates="user",
        cascade="all, delete-orphan",   # delete skills when user is deleted
        lazy="selectin",                # async-safe loading strategy
    )
    wanted_skills: Mapped[List["UserSkillWanted"]] = relationship(
        "UserSkillWanted",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    matches_as_a: Mapped[List["Match"]] = relationship(
        "Match",
        foreign_keys="Match.user_a_id",
        back_populates="user_a",
        lazy="selectin",
    )
    matches_as_b: Mapped[List["Match"]] = relationship(
        "Match",
        foreign_keys="Match.user_b_id",
        back_populates="user_b",
        lazy="selectin",
    )

    # ── Composite Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        # Composite index for college + is_active → "active users at my college"
        Index("ix_users_college_active", "college", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
