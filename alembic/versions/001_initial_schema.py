"""Initial schema — users, skills, user_skills_offered, user_skills_wanted, matches

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── clean up any partial state from a previous failed run ─────────────
    # If the migration crashed midway, some objects may already exist but
    # alembic_version was never updated. Drop everything we're about to
    # create so we always start clean. Safe on a fresh DB (IF EXISTS = no-op).
    op.execute("DROP TABLE IF EXISTS matches CASCADE")
    op.execute("DROP TABLE IF EXISTS user_skills_wanted CASCADE")
    op.execute("DROP TABLE IF EXISTS user_skills_offered CASCADE")
    op.execute("DROP TABLE IF EXISTS skills CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TYPE IF EXISTS match_status_enum")
    op.execute("DROP TYPE IF EXISTS urgency_level_enum")
    op.execute("DROP TYPE IF EXISTS proficiency_level_enum")

    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("college", sa.String(255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_college", "users", ["college"])
    op.create_index("ix_users_college_active", "users", ["college", "is_active"])

    # ── skills ─────────────────────────────────────────────────────────────
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_skills_name", "skills", ["name"], unique=True)
    op.create_index("ix_skills_category", "skills", ["category"])

    # ── enum types ──────────────────────────────────────────────────────────
    # Safe to use plain CREATE TYPE here — the DROP IF EXISTS block above
    # guarantees these types don't exist at this point.
    op.execute("CREATE TYPE proficiency_level_enum AS ENUM ('BEGINNER', 'INTERMEDIATE', 'EXPERT')")
    op.execute("CREATE TYPE urgency_level_enum AS ENUM ('LOW', 'MEDIUM', 'HIGH')")
    op.execute("CREATE TYPE match_status_enum AS ENUM ('PENDING', 'ACCEPTED', 'REJECTED', 'COMPLETED')")

    # ── user_skills_offered ────────────────────────────────────────────────
    op.create_table(
        "user_skills_offered",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("proficiency_level",
                  postgresql.ENUM("beginner", "intermediate", "expert", name="proficiency_level_enum", create_type=False),
                  nullable=False, server_default="INTERMEDIATE"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_offered_user_skill"),
    )
    op.create_index("ix_uso_user_id", "user_skills_offered", ["user_id"])
    op.create_index("ix_uso_skill_id", "user_skills_offered", ["skill_id"])

    # ── user_skills_wanted ─────────────────────────────────────────────────
    op.create_table(
        "user_skills_wanted",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("urgency",
                  postgresql.ENUM("low", "medium", "high", name="urgency_level_enum", create_type=False),
                  nullable=False, server_default="MEDIUM"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_wanted_user_skill"),
    )
    op.create_index("ix_usw_user_id", "user_skills_wanted", ["user_id"])
    op.create_index("ix_usw_skill_id", "user_skills_wanted", ["skill_id"])

    # ── matches ────────────────────────────────────────────────────────────
    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_a_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_b_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_offered_by_a", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("skill_offered_by_b", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status",
                  postgresql.ENUM("pending", "accepted", "rejected", "completed",
                                  name="match_status_enum", create_type=False),
                  nullable=False, server_default="PENDING"),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_match_pair"),
        sa.CheckConstraint("user_a_id != user_b_id", name="ck_match_no_self"),
    )
    op.create_index("ix_matches_user_a", "matches", ["user_a_id"])
    op.create_index("ix_matches_user_b", "matches", ["user_b_id"])
    op.create_index("ix_matches_user_a_status", "matches", ["user_a_id", "status"])
    op.create_index("ix_matches_user_b_status", "matches", ["user_b_id", "status"])
    op.create_index("ix_matches_score_desc", "matches", ["match_score"])
    op.create_index("ix_matches_status", "matches", ["status"])


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("user_skills_wanted")
    op.drop_table("user_skills_offered")
    op.drop_table("skills")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS match_status_enum")
    op.execute("DROP TYPE IF EXISTS urgency_level_enum")
    op.execute("DROP TYPE IF EXISTS proficiency_level_enum")
