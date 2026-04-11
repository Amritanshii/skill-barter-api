"""
User Pydantic schemas.

Separation of concerns:
  UserCreate      → validated input for POST /auth/register
  UserLogin       → validated input for POST /auth/login
  UserPublic      → safe outbound representation (no password hash)
  UserProfile     → full profile including offered/wanted skills
  UserProfileUpdate → PATCH body (all fields optional)

Why separate schemas instead of one model?
  - Never accidentally expose hashed_password in a response.
  - Different endpoints need different subsets; one mega-schema creates
    confusing required/optional noise in the Swagger UI.
"""

import re
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.user_skill import OfferedSkillPublic, WantedSkillPublic


# ── Helpers ───────────────────────────────────────────────────────────────────

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,50}$")
PASSWORD_MIN_LENGTH = 8


# ── Request Schemas ───────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    """
    POST /auth/register  request body.

    Validates:
    - email     : valid RFC-5322 address via Pydantic's EmailStr
    - username  : lowercase alphanumeric + underscore, 3–50 chars
    - password  : min 8 chars; must contain at least one digit
    - full_name : optional free text
    - college   : optional

    Example request:
        {
          "email": "alice@mit.edu",
          "username": "alice_codes",
          "password": "SecurePass1",
          "full_name": "Alice Smith",
          "college": "MIT"
        }
    """

    email: EmailStr = Field(..., description="Must be a valid email address")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH)
    full_name: Optional[str] = Field(None, max_length=255)
    college: Optional[str] = Field(None, max_length=255)

    @field_validator("username")
    @classmethod
    def username_must_be_lowercase_alphanumeric(cls, v: str) -> str:
        v = v.lower().strip()
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3–50 characters, lowercase letters, "
                "digits, or underscores only."
            )
        return v

    @field_validator("password")
    @classmethod
    def password_must_contain_digit(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "email": "alice@mit.edu",
            "username": "alice_codes",
            "password": "SecurePass1",
            "full_name": "Alice Smith",
            "college": "MIT",
        }
    }}


class UserLogin(BaseModel):
    """
    POST /auth/login  request body.

    We accept email OR username to be user-friendly.
    The service layer tries email first, then username.

    Example request:
        { "identifier": "alice@mit.edu", "password": "SecurePass1" }
    """

    identifier: str = Field(
        ...,
        description="Email address OR username",
        examples=["alice@mit.edu", "alice_codes"],
    )
    password: str = Field(..., min_length=1)


# ── Response Schemas ──────────────────────────────────────────────────────────

class UserPublic(BaseModel):
    """
    Safe outbound user representation — used in lists and match results.
    hashed_password is intentionally absent.
    """

    id: str
    email: EmailStr
    username: str
    full_name: Optional[str]
    college: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}   # enables ORM mode


class UserProfile(UserPublic):
    """
    Extended profile that includes offered and wanted skills.
    Returned by GET /users/me/profile.
    """

    offered_skills: List[OfferedSkillPublic] = []
    wanted_skills: List[WantedSkillPublic] = []

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    """
    PATCH /users/me/profile  request body.
    All fields are optional — only provided fields are updated.

    Example request:
        { "bio": "CS junior at MIT, love building side projects" }
    """

    full_name: Optional[str] = Field(None, max_length=255)
    college: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None, max_length=2000)
    avatar_url: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserProfileUpdate":
        if all(v is None for v in self.model_dump().values()):
            raise ValueError("At least one field must be provided for update.")
        return self
