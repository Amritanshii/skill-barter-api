"""
JWT Auth schemas.

TokenResponse  → what the /login endpoint returns to the client.
TokenPayload   → the decoded claims we store inside the JWT.
"""

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """
    Response body for POST /auth/login and POST /auth/refresh.

    access_token  : short-lived JWT (30 min) — used in Authorization header
    refresh_token : long-lived JWT (7 days) — used only to mint new access tokens
    token_type    : always "bearer"
    """

    access_token: str = Field(
        ...,
        description="Short-lived JWT (30 min). Send as 'Authorization: Bearer <token>'",
    )
    refresh_token: str = Field(
        ...,
        description="Long-lived JWT (7 days). Use to obtain a new access token.",
    )
    token_type: str = Field(default="bearer")


class TokenPayload(BaseModel):
    """
    The claims embedded inside our JWTs.

    sub  : subject = user's UUID (standard JWT claim)
    jti  : JWT ID   = unique UUID per token (used for blacklisting on logout)
    exp  : expiry   = Unix timestamp (set by python-jose automatically)
    type : 'access' or 'refresh' — prevent using a refresh token as access
    """

    sub: str = Field(..., description="User UUID")
    jti: str = Field(..., description="Unique token ID for blacklisting")
    type: str = Field(..., description="'access' or 'refresh'")
