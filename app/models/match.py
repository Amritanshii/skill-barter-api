"""
Match model — represents a confirmed bidirectional skill-exchange pair.

Design decisions:
- We always store the pair with the lower UUID as user_a to prevent storing
  the same match twice in different orderings. This is enforced in the service
  layer (not DB level) for portability.
- UNIQUE(user_a_id, user_b_id) still guards against duplicates at DB level.
- match_score (0.0–1.0) is computed by the matching engine and stored so we
  can re-sort without recomputing.
- skill_offered_by_a / skill_offered_by_b record the *primary* skills that
  triggered the match. A user may share multiple skills but we highlight one
  pair. Full details come from user_skills_offered/wanted.
- status tracks the lifecycle: pending → accepted / rejected → completed.
- initiated_by records which user triggered the first contact.
"""

import enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.skill import Skill


class MatchStatus(str, enum.Enum):
    """
    Lifecycle states of a match.

    pending   → The system found a match; neither user has responded.
    accepted  → Both (or one, depending on business logic) accepted.
    rejected  → At least one user declined.
    completed → The exchange took place and was marked done.
    """
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    REJECTED  = "rejected"
    COMPLETED = "completed"


class Match(Base, TimestampMixin):
    """
    A bidirectional skill-exchange match between two users.

    user_a offers skill_offered_by_a  →  user_b wants it
    user_b offers skill_offered_by_b  →  user_a wants it

    Invariant (enforced at service layer):
        user_a_id < user_b_id  (lexicographic on UUID string)
    This guarantees each pair has exactly one row.
    """

    __tablename__ = "matches"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
    )

    # ── Participants ──────────────────────────────────────────────────────────
    user_a_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Always the lexicographically smaller UUID of the pair",
    )
    user_b_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Skills that triggered the match ───────────────────────────────────────
    skill_offered_by_a: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The skill A offers that B wants (primary match driver)",
    )
    skill_offered_by_b: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The skill B offers that A wants (primary match driver)",
    )

    # ── Scoring & Status ──────────────────────────────────────────────────────
    match_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="0.0 – 1.0; higher = more mutual skill overlap",
    )
    status: Mapped[MatchStatus] = mapped_column(
        SAEnum(MatchStatus, name="match_status_enum"),
        nullable=False,
        default=MatchStatus.PENDING,
        index=True,
        comment="Current lifecycle state of this match",
    )

    # ── Provenance ────────────────────────────────────────────────────────────
    initiated_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Which user triggered the first contact; NULL = system-generated",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user_a: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_a_id],
        back_populates="matches_as_a",
        lazy="selectin",
    )
    user_b: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_b_id],
        back_populates="matches_as_b",
        lazy="selectin",
    )
    skill_a: Mapped["Skill"] = relationship(
        "Skill",
        foreign_keys=[skill_offered_by_a],
        lazy="selectin",
    )
    skill_b: Mapped["Skill"] = relationship(
        "Skill",
        foreign_keys=[skill_offered_by_b],
        lazy="selectin",
    )

    # ── Constraints & Indexes ─────────────────────────────────────────────────
    __table_args__ = (
        # One row per pair — prevents duplicate matches at DB level
        UniqueConstraint("user_a_id", "user_b_id", name="uq_match_pair"),

        # "Show all matches for user X" — covers both sides of the match
        Index("ix_matches_user_a", "user_a_id"),
        Index("ix_matches_user_b", "user_b_id"),

        # Composite index for "active matches for user X"
        Index("ix_matches_user_a_status", "user_a_id", "status"),
        Index("ix_matches_user_b_status", "user_b_id", "status"),

        # Score-descending index for sorted match feeds
        Index("ix_matches_score_desc", "match_score"),

        # Sanity check: a user cannot match with themselves
        CheckConstraint("user_a_id != user_b_id", name="ck_match_no_self"),
    )

    def __repr__(self) -> str:
        return (
            f"<Match id={self.id} "
            f"a={self.user_a_id} b={self.user_b_id} "
            f"score={self.match_score:.2f} status={self.status}>"
        )

    # ── Helper ────────────────────────────────────────────────────────────────
    def other_user_id(self, current_user_id: str) -> str:
        """Return the *other* participant's ID for a given user."""
        return self.user_b_id if self.user_a_id == current_user_id else self.user_a_id
