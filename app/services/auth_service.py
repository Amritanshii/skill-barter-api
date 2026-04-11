"""
Authentication service — all auth business logic lives here.

Separation from the router:
  The router handles HTTP concerns (request/response shapes, status codes).
  The service handles business logic (validation, DB queries, token creation).
  This makes the service independently testable without spinning up FastAPI.

Methods:
  register   → validate uniqueness → hash password → create user → mint tokens
  login      → find user by email/username → verify password → mint tokens
  logout     → decode token → blacklist jti in Redis
  refresh    → verify refresh token → blacklist old → mint new pair
"""

import structlog
from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import RedisKeys
from app.core.security import (
    create_token_pair,
    decode_token,
    get_token_expiry_seconds,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate

logger = structlog.get_logger(__name__)


class AuthService:

    # ── Register ──────────────────────────────────────────────────────────────

    @staticmethod
    async def register(
        db: AsyncSession,
        redis: Redis,
        payload: UserCreate,
    ) -> tuple[User, TokenResponse]:
        """
        Create a new user account.

        Raises 409 if email or username already exists.
        Returns the new User ORM object and a fresh token pair.
        """
        # Check uniqueness
        existing = await db.execute(
            select(User).where(
                or_(User.email == payload.email, User.username == payload.username)
            )
        )
        existing_user = existing.scalar_one_or_none()
        if existing_user:
            field = "email" if existing_user.email == payload.email else "username"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An account with this {field} already exists.",
            )

        # Create user
        user = User(
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            college=payload.college,
        )
        db.add(user)
        await db.flush()   # assigns user.id without committing

        # Seed empty Redis skill sets for this new user
        # (matching engine expects these keys to exist)
        await redis.delete(
            RedisKeys.user_offered_skills(user.id),
            RedisKeys.user_wanted_skills(user.id),
        )

        tokens = create_token_pair(user.id)
        logger.info("user_registered", user_id=user.id, email=user.email)
        return user, tokens

    # ── Login ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def login(
        db: AsyncSession,
        identifier: str,
        password: str,
    ) -> tuple[User, TokenResponse]:
        """
        Authenticate a user by email OR username + password.

        Returns the User + token pair on success.
        Raises 401 with a deliberately vague message (don't leak which field
        was wrong — that helps enumeration attacks).
        """
        _invalid = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

        # Try email first, then username
        result = await db.execute(
            select(User).where(
                or_(User.email == identifier, User.username == identifier)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            # Still call verify_password to prevent timing-attack enumeration
            verify_password(password, "$2b$12$placeholder_hash_for_timing")
            raise _invalid

        if not verify_password(password, user.hashed_password):
            raise _invalid

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated. Contact support.",
            )

        tokens = create_token_pair(user.id)
        logger.info("user_logged_in", user_id=user.id)
        return user, tokens

    # ── Logout ────────────────────────────────────────────────────────────────

    @staticmethod
    async def logout(redis: Redis, access_token: str) -> None:
        """
        Blacklist the JWT by storing its jti in Redis.
        The key TTL matches the token's remaining validity — it auto-expires.

        Why not just delete sessions?
          JWTs are stateless — we can't "delete" them without a blacklist.
          The blacklist entry lives only as long as the token would be valid,
          so Redis memory stays bounded.
        """
        try:
            payload = decode_token(access_token)
            ttl = get_token_expiry_seconds(access_token)
            if ttl > 0:
                await redis.setex(
                    RedisKeys.blacklisted_token(payload.jti),
                    ttl,
                    "1",
                )
            logger.info("user_logged_out", jti=payload.jti)
        except Exception as exc:
            # Don't raise — logout should always succeed from the user's perspective
            logger.warning("logout_token_decode_failed", error=str(exc))

    # ── Refresh token ─────────────────────────────────────────────────────────

    @staticmethod
    async def refresh(
        db: AsyncSession,
        redis: Redis,
        refresh_token: str,
    ) -> TokenResponse:
        """
        Exchange a valid refresh token for a new access + refresh token pair.
        The old refresh token is blacklisted immediately (rotation).

        Token rotation prevents refresh token replay: if an attacker steals
        a refresh token and tries to reuse it after the user already rotated,
        the blacklist check will catch it.
        """
        from jose import JWTError

        _invalid = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )
        try:
            payload = decode_token(refresh_token)
        except JWTError:
            raise _invalid

        if payload.type != "refresh":
            raise _invalid

        # Check blacklist
        if await redis.exists(RedisKeys.blacklisted_token(payload.jti)):
            raise _invalid

        # Load user
        result = await db.execute(select(User).where(User.id == payload.sub))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise _invalid

        # Rotate: blacklist old refresh token
        old_ttl = get_token_expiry_seconds(refresh_token)
        if old_ttl > 0:
            await redis.setex(
                RedisKeys.blacklisted_token(payload.jti), old_ttl, "1"
            )

        new_tokens = create_token_pair(user.id)
        logger.info("token_refreshed", user_id=user.id)
        return new_tokens
