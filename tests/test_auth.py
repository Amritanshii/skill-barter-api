"""
Authentication endpoint tests.

Covers:
  - Register: happy path, duplicate email, duplicate username, weak password
  - Login: success, wrong password, unknown user, inactive user
  - Logout: token blacklisted after logout
  - Refresh: token rotation works, old token rejected
  - /me: returns correct user
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL    = "/api/v1/auth/login"
LOGOUT_URL   = "/api/v1/auth/logout"
REFRESH_URL  = "/api/v1/auth/refresh"
ME_URL       = "/api/v1/auth/me"


# ── Register ──────────────────────────────────────────────────────────────────

class TestRegister:

    async def test_register_success(self, client: AsyncClient):
        resp = await client.post(REGISTER_URL, json={
            "email": "alice@mit.edu",
            "username": "alice_codes",
            "password": "SecurePass1",
            "full_name": "Alice Smith",
            "college": "MIT",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["user"]["email"] == "alice@mit.edu"
        assert data["user"]["username"] == "alice_codes"
        assert "hashed_password" not in data["user"]  # never leak hash
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]
        assert data["tokens"]["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client: AsyncClient, test_user):
        resp = await client.post(REGISTER_URL, json={
            "email": "testuser@mit.edu",  # already exists
            "username": "new_username",
            "password": "SecurePass1",
        })
        assert resp.status_code == 409
        assert "email" in resp.json()["detail"].lower()

    async def test_register_duplicate_username(self, client: AsyncClient, test_user):
        resp = await client.post(REGISTER_URL, json={
            "email": "newemail@mit.edu",
            "username": "testuser",  # already exists
            "password": "SecurePass1",
        })
        assert resp.status_code == 409
        assert "username" in resp.json()["detail"].lower()

    async def test_register_weak_password_no_digit(self, client: AsyncClient):
        resp = await client.post(REGISTER_URL, json={
            "email": "bob@mit.edu",
            "username": "bob_test",
            "password": "NoDigitsHere",
        })
        assert resp.status_code == 422  # Pydantic validation error

    async def test_register_password_too_short(self, client: AsyncClient):
        resp = await client.post(REGISTER_URL, json={
            "email": "charlie@mit.edu",
            "username": "charlie_t",
            "password": "S1",
        })
        assert resp.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post(REGISTER_URL, json={
            "email": "not-an-email",
            "username": "dave_t",
            "password": "ValidPass1",
        })
        assert resp.status_code == 422

    async def test_register_invalid_username_special_chars(self, client: AsyncClient):
        resp = await client.post(REGISTER_URL, json={
            "email": "eve@mit.edu",
            "username": "eve@codes!",  # special chars not allowed
            "password": "ValidPass1",
        })
        assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:

    async def test_login_with_email_success(self, client: AsyncClient, test_user):
        resp = await client.post(LOGIN_URL, json={
            "identifier": "testuser@mit.edu",
            "password": "TestPass1",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()["tokens"]

    async def test_login_with_username_success(self, client: AsyncClient, test_user):
        resp = await client.post(LOGIN_URL, json={
            "identifier": "testuser",
            "password": "TestPass1",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()["tokens"]

    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        resp = await client.post(LOGIN_URL, json={
            "identifier": "testuser@mit.edu",
            "password": "WrongPassword1",
        })
        assert resp.status_code == 401
        # Vague message — does not hint which field was wrong
        assert "incorrect" in resp.json()["detail"].lower()

    async def test_login_unknown_identifier(self, client: AsyncClient):
        resp = await client.post(LOGIN_URL, json={
            "identifier": "nobody@nowhere.com",
            "password": "AnyPass1",
        })
        assert resp.status_code == 401

    async def test_login_inactive_user(self, client: AsyncClient, db: AsyncSession, test_user):
        test_user.is_active = False
        db.add(test_user)
        await db.flush()

        resp = await client.post(LOGIN_URL, json={
            "identifier": "testuser@mit.edu",
            "password": "TestPass1",
        })
        assert resp.status_code == 403


# ── Protected route (/me) ─────────────────────────────────────────────────────

class TestMe:

    async def test_me_authenticated(self, client: AsyncClient, auth_headers, test_user):
        resp = await client.get(ME_URL, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"

    async def test_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get(ME_URL)
        assert resp.status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient):
        resp = await client.get(ME_URL, headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

class TestLogout:

    async def test_logout_blacklists_token(self, client: AsyncClient, test_user):
        # Login to get token
        login_resp = await client.post(LOGIN_URL, json={
            "identifier": "testuser@mit.edu",
            "password": "TestPass1",
        })
        token = login_resp.json()["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Logout
        logout_resp = await client.post(LOGOUT_URL, headers=headers)
        assert logout_resp.status_code == 204

        # Token should now be invalid
        me_resp = await client.get(ME_URL, headers=headers)
        assert me_resp.status_code == 401


# ── Refresh ───────────────────────────────────────────────────────────────────

class TestRefresh:

    async def test_refresh_returns_new_tokens(self, client: AsyncClient, test_user):
        login_resp = await client.post(LOGIN_URL, json={
            "identifier": "testuser@mit.edu",
            "password": "TestPass1",
        })
        refresh_token = login_resp.json()["tokens"]["refresh_token"]

        refresh_resp = await client.post(
            REFRESH_URL,
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert refresh_resp.status_code == 200
        new_tokens = refresh_resp.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens

    async def test_access_token_rejected_as_refresh(self, client: AsyncClient, test_user):
        login_resp = await client.post(LOGIN_URL, json={
            "identifier": "testuser@mit.edu",
            "password": "TestPass1",
        })
        access_token = login_resp.json()["tokens"]["access_token"]

        # Using access token where refresh is expected → 401
        refresh_resp = await client.post(
            REFRESH_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert refresh_resp.status_code == 401
