"""
FastAPI dependency injection (DI) functions.

Why DI?
  FastAPI's Depends() system is the recommended way to share resources
  (DB session, Redis client, current user) across routes without global
  state or passing objects manually through every function call.

  Each dependency is testable independently — in tests, swap get_db()
  with a fixture that uses an in-memory SQLite or a rolled-back transaction.

Dependencies defined here:
  get_db          → AsyncSession (one per request, from database.py)
  get_redis       → aioredis.Redis (pool-backed, from redis_client.py)
  get_current_user     → User  (decoded JWT → DB lookup)
  get_current_active_user → User  (same + checks is_active)
"""

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import RedisKeys, get_redis
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

logger = structlog.get_logger(__name__)

# ── Auth scheme ───────────────────────────────────────────────────────────────

# HTTPBearer extracts the token from "Authorization: Bearer <token>" header.
# auto_error=False lets us return a cleaner 401 message instead of a generic one.
bearer_scheme = HTTPBearer(auto_error=False)


# ── Current User Dependency ───────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User:
    """
    Validate JWT and return the authenticated User object.

    Steps:
      1. Extract Bearer token from Authorization header
      2. Decode + verify JWT signature and expiry
      3. Verify token type is 'access' (not a refresh token misuse)
      4. Check Redis blacklist — reject if token was explicitly logged out
      5. Load user from PostgreSQL by user_id (sub claim)
      6. Raise HTTP 401 at any failure step

    Why check the blacklist on every request?
      JWTs are stateless — once issued, they're valid until expiry.
      Without a blacklist, a logged-out user's token remains usable.
      Redis check adds ~1ms latency but provides real logout security.

    Usage in a router:
        @router.get("/protected")
        async def protected(user: User = Depends(get_current_user)):
            return {"hello": user.username}
    """
    _credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Step 1: Token must be present
    if not credentials:
        raise _credentials_exception

    token = credentials.credentials

    # Step 2 + 3: Decode and validate token
    try:
        payload = decode_token(token)
    except JWTError as exc:
        logger.warning("jwt_decode_failed", error=str(exc))
        raise _credentials_exception

    if payload.type != "access":
        logger.warning("wrong_token_type", token_type=payload.type)
        raise _credentials_exception

    # Step 4: Check blacklist (logout support)
    blacklist_key = RedisKeys.blacklisted_token(payload.jti)
    if await redis.exists(blacklist_key):
        logger.warning("blacklisted_token_used", jti=payload.jti)
        raise _credentials_exception

    # Step 5: Load user from DB
    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("token_user_not_found", user_id=payload.sub)
        raise _credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Same as get_current_user but additionally rejects deactivated accounts.
    Use this on all business endpoints (not just auth endpoints).

    Why separate from get_current_user?
      Allows admin endpoints to accept deactivated users for management,
      while all regular endpoints automatically enforce the is_active check.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact support.",
        )
    return current_user


# ── Type aliases ──────────────────────────────────────────────────────────────
# Use these Annotated types in router function signatures for brevity.
# FastAPI reads the Depends() inside Annotated automatically.

CurrentUser = Annotated[User, Depends(get_current_active_user)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
