"""
Security utilities: JWT creation/verification and bcrypt password hashing.

Design decisions:
- We issue TWO tokens: a short-lived access token (30 min) and a long-lived
  refresh token (7 days). This is the industry-standard approach:
    * Short access tokens limit the damage if a token is stolen.
    * Refresh tokens let users stay logged in without re-entering credentials.
- Each token has a unique 'jti' (JWT ID). On logout, we store jti in Redis
  with a TTL matching the token expiry — this is our token blacklist.
  Checking Redis on every request adds ~1ms latency but prevents replay attacks.
- bcrypt with work factor 12 is the gold standard for password storage.
  Factor 12 means ~300ms per hash on modern hardware — slow enough to deter
  brute-force attacks, fast enough to not annoy users at login.

Interview note: "Why not RS256?"
  HS256 is fine for a monolith where the same service signs and verifies.
  RS256 is better for microservices where multiple services verify tokens
  issued by a central auth service (no need to share the private key).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.schemas.auth import TokenPayload, TokenResponse

settings = get_settings()

# ── Password Hashing ──────────────────────────────────────────────────────────

# CryptContext manages which algorithms are active and deprecated.
# schemes=["bcrypt"]: only bcrypt is used for new hashes.
# deprecated="auto": automatically upgrades hashes from old algorithms on next login.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt.
    The returned hash includes the salt (bcrypt embeds it).
    Always store this hash, NEVER the plain password.
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Securely compare plain_password against a stored bcrypt hash.
    Uses constant-time comparison internally — immune to timing attacks.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT Helpers ───────────────────────────────────────────────────────────────

def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    """
    Internal: create a signed JWT with standard + custom claims.

    Claims:
      sub   = user UUID (standard)
      jti   = unique token ID (for blacklisting)
      type  = 'access' or 'refresh' (custom — prevents misuse)
      exp   = expiry (standard, set automatically)
      iat   = issued-at (standard, useful for debugging)
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "jti": str(uuid.uuid4()),   # unique per token
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: str) -> str:
    """Create a 30-minute access token for the given user ID."""
    return _create_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str) -> str:
    """Create a 7-day refresh token for the given user ID."""
    return _create_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_token_pair(user_id: str) -> TokenResponse:
    """
    Convenience: create both tokens at once.
    Called after successful login or registration.
    """
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        token_type="bearer",
    )


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT.

    Raises JWTError (from python-jose) on:
      - Invalid signature
      - Expired token
      - Malformed token

    The caller (get_current_user dependency) catches JWTError and raises
    HTTP 401.
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    return TokenPayload(
        sub=payload["sub"],
        jti=payload["jti"],
        type=payload["type"],
    )


def get_token_expiry_seconds(token: str) -> int:
    """
    Return how many seconds until this token expires.
    Used when blacklisting on logout — we set the Redis TTL to match.
    This ensures the blacklist entry auto-cleans itself.
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    exp = payload.get("exp", 0)
    now = int(datetime.now(timezone.utc).timestamp())
    remaining = exp - now
    return max(remaining, 0)   # never negative
