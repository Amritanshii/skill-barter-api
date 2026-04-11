"""
Base model class shared by all SQLAlchemy models.

Why a custom Base?
- Centralises the metadata object (needed for Alembic migrations).
- Gives every table a consistent __repr__ for debugging.
- timestamp mixin adds created_at / updated_at to every model that
  inherits from it without repetition.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Single metadata registry for all models."""
    pass


class TimestampMixin:
    """
    Adds created_at and updated_at columns to any model.

    - created_at  uses server_default so the DB sets it on INSERT.
    - updated_at  uses onupdate so SQLAlchemy refreshes it on every UPDATE.
    Both store timezone-aware UTC datetimes.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def generate_uuid() -> str:
    """Generate a UUID4 string — used as the default for primary keys."""
    return str(uuid.uuid4())
