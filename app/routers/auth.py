"""
Auth router — /api/v1/auth/*

Endpoints:
  POST /register  → create account, return tokens
  POST /login     → authenticate, return tokens
  POST /logout    → blacklist current token
  POST /refresh   → exchange refresh token for new pair
  GET  /me        → return current user profile
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies import CurrentUser, DBSession, RedisClient
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate, UserLogin, UserPublic
from app.services.auth_service import AuthService

router = APIRouter()
settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


@router.post(
    "/register",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description=(
        "Creates a new user and returns a JWT access + refresh token pair. "
        "Email and username must be unique. Password must be ≥8 chars and contain a digit."
    ),
)
async def register(
    payload: UserCreate,
    db: DBSession,
    redis: RedisClient,
):
    """
    Register a new college student account.

    Request body:
        {
          "email": "alice@mit.edu",
          "username": "alice_codes",
          "password": "SecurePass1",
          "full_name": "Alice Smith",
          "college": "MIT"
        }

    Response 201:
        {
          "user": { ...UserPublic... },
          "tokens": {
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",
            "token_type": "bearer"
          }
        }
    """
    user, tokens = await AuthService.register(db, redis, payload)
    return {
        "user": UserPublic.model_validate(user),
        "tokens": tokens,
    }


@router.post(
    "/login",
    response_model=dict,
    summary="Login with email/username and password",
)
async def login(
    payload: UserLogin,
    db: DBSession,
    redis: RedisClient,
):
    """
    Authenticate and receive JWT tokens.

    Request body:
        { "identifier": "alice@mit.edu", "password": "SecurePass1" }
      OR
        { "identifier": "alice_codes",  "password": "SecurePass1" }

    Response 200:
        {
          "user": { ...UserPublic... },
          "tokens": {
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",
            "token_type": "bearer"
          }
        }
    """
    user, tokens = await AuthService.login(db, payload.identifier, payload.password)
    return {
        "user": UserPublic.model_validate(user),
        "tokens": tokens,
    }


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout — blacklist the current access token",
)
async def logout(
    current_user: CurrentUser,
    redis: RedisClient,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """
    Invalidate the current JWT.

    After calling this endpoint, the access token is added to a Redis
    blacklist with a TTL matching its remaining validity.
    Any subsequent request with the same token returns 401.

    No request body needed — uses the Bearer token from the Authorization header.
    """
    if credentials:
        await AuthService.logout(redis, credentials.credentials)
    return None


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new token pair",
)
async def refresh_token(
    db: DBSession,
    redis: RedisClient,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """
    Rotate tokens: provide a valid refresh token, receive a new access + refresh pair.
    The old refresh token is immediately blacklisted (cannot be reused).

    Send the refresh token (not the access token) in the Authorization header:
        Authorization: Bearer <refresh_token>
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required.",
        )
    return await AuthService.refresh(db, redis, credentials.credentials)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get the currently authenticated user",
)
async def get_me(current_user: CurrentUser):
    """
    Returns the profile of the currently logged-in user.
    Requires a valid access token in the Authorization header.
    """
    return UserPublic.model_validate(current_user)
