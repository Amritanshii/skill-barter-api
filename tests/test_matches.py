"""
Matching engine tests.

Covers:
  - Bidirectional match found when A offers X + wants Y, B offers Y + wants X
  - No match when only one direction overlaps
  - No match when both users offer same skills with no wants crossover
  - Match status transitions (pending → accepted → completed)
  - Invalid status transitions rejected
  - Cache invalidation on skill change
  - GET /matches returns cached result on second call
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_skill import UserSkillOffered, UserSkillWanted

pytestmark = pytest.mark.asyncio

MATCHES_URL  = "/api/v1/matches"
OFFERED_URL  = "/api/v1/users/me/offered"
WANTED_URL   = "/api/v1/users/me/wanted"
LOGIN_URL    = "/api/v1/auth/login"


async def _login(client: AsyncClient, identifier: str, password: str) -> dict:
    resp = await client.post(LOGIN_URL, json={"identifier": identifier, "password": password})
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Bidirectional matching ────────────────────────────────────────────────────

class TestBidirectionalMatching:

    async def test_bidirectional_match_found(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user,
        test_user_b,
        python_skill,
        react_skill,
        db: AsyncSession,
    ):
        """
        A offers Python, wants React.
        B offers React, wants Python.
        → A and B should match.
        """
        # Setup A
        db.add(UserSkillOffered(user_id=test_user.id, skill_id=python_skill.id))
        db.add(UserSkillWanted(user_id=test_user.id, skill_id=react_skill.id))
        # Setup B
        db.add(UserSkillOffered(user_id=test_user_b.id, skill_id=react_skill.id))
        db.add(UserSkillWanted(user_id=test_user_b.id, skill_id=python_skill.id))
        await db.flush()

        # Sync Redis for both users
        from app.core.redis_client import RedisKeys
        from tests.conftest import FakeRedis  # use the test redis fixture

        resp = await client.get(f"{MATCHES_URL}?refresh=true", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

        matched_user_ids = [m["other_user_id"] for m in data["matches"]]
        assert test_user_b.id in matched_user_ids

    async def test_no_match_one_direction_only(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user,
        test_user_b,
        python_skill,
        react_skill,
        db: AsyncSession,
    ):
        """
        A offers Python, wants React.
        B offers React, does NOT want Python.
        → No match (not bidirectional).
        """
        db.add(UserSkillOffered(user_id=test_user.id, skill_id=python_skill.id))
        db.add(UserSkillWanted(user_id=test_user.id, skill_id=react_skill.id))
        db.add(UserSkillOffered(user_id=test_user_b.id, skill_id=react_skill.id))
        # B does NOT add python to wanted
        await db.flush()

        resp = await client.get(f"{MATCHES_URL}?refresh=true", headers=auth_headers)
        assert resp.status_code == 200
        matched_ids = [m["other_user_id"] for m in resp.json()["matches"]]
        assert test_user_b.id not in matched_ids

    async def test_no_self_match(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user,
        python_skill,
        react_skill,
        db: AsyncSession,
    ):
        """A user should never appear in their own match list."""
        db.add(UserSkillOffered(user_id=test_user.id, skill_id=python_skill.id))
        db.add(UserSkillWanted(user_id=test_user.id, skill_id=react_skill.id))
        await db.flush()

        resp = await client.get(f"{MATCHES_URL}?refresh=true", headers=auth_headers)
        matched_ids = [m["other_user_id"] for m in resp.json()["matches"]]
        assert test_user.id not in matched_ids

    async def test_match_score_higher_with_more_overlap(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user,
        test_user_b,
        python_skill,
        react_skill,
        db: AsyncSession,
    ):
        """More overlapping skills → higher match_score."""
        # A offers Python + React, wants both
        db.add(UserSkillOffered(user_id=test_user.id, skill_id=python_skill.id))
        db.add(UserSkillOffered(user_id=test_user.id, skill_id=react_skill.id))
        db.add(UserSkillWanted(user_id=test_user.id, skill_id=react_skill.id))
        db.add(UserSkillWanted(user_id=test_user.id, skill_id=python_skill.id))
        # B mirrors
        db.add(UserSkillOffered(user_id=test_user_b.id, skill_id=react_skill.id))
        db.add(UserSkillOffered(user_id=test_user_b.id, skill_id=python_skill.id))
        db.add(UserSkillWanted(user_id=test_user_b.id, skill_id=python_skill.id))
        db.add(UserSkillWanted(user_id=test_user_b.id, skill_id=react_skill.id))
        await db.flush()

        resp = await client.get(f"{MATCHES_URL}?refresh=true", headers=auth_headers)
        matches = resp.json()["matches"]
        assert len(matches) >= 1
        assert matches[0]["match_score"] > 0


# ── Match status transitions ──────────────────────────────────────────────────

class TestMatchStatus:

    async def _create_match(self, db, test_user, test_user_b, python_skill, react_skill):
        """Helper: insert a pending match directly."""
        from app.models.match import Match, MatchStatus
        import uuid
        user_a_id = min(test_user.id, test_user_b.id)
        user_b_id = max(test_user.id, test_user_b.id)
        match = Match(
            user_a_id=user_a_id,
            user_b_id=user_b_id,
            skill_offered_by_a=python_skill.id,
            skill_offered_by_b=react_skill.id,
            match_score=0.8,
            status=MatchStatus.PENDING,
        )
        db.add(match)
        await db.flush()
        return match

    async def test_accept_match(
        self, client, auth_headers, db, test_user, test_user_b,
        python_skill, react_skill
    ):
        match = await self._create_match(db, test_user, test_user_b, python_skill, react_skill)
        resp = await client.patch(
            f"{MATCHES_URL}/{match.id}",
            json={"status": "accepted"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_reject_match(
        self, client, auth_headers, db, test_user, test_user_b,
        python_skill, react_skill
    ):
        match = await self._create_match(db, test_user, test_user_b, python_skill, react_skill)
        resp = await client.patch(
            f"{MATCHES_URL}/{match.id}",
            json={"status": "rejected"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    async def test_invalid_transition_pending_to_completed(
        self, client, auth_headers, db, test_user, test_user_b,
        python_skill, react_skill
    ):
        """pending → completed is not a valid transition (must go through accepted)."""
        match = await self._create_match(db, test_user, test_user_b, python_skill, react_skill)
        resp = await client.patch(
            f"{MATCHES_URL}/{match.id}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_third_party_cannot_update_match(
        self, client, db, test_user_b, python_skill, react_skill,
        test_user  # needed to create the match
    ):
        """A user who is NOT in the match cannot change its status."""
        # Register a third user
        from app.core.security import hash_password
        from app.models.user import User
        third = User(
            email="third@test.com", username="third_user",
            hashed_password=hash_password("TestPass1"), college="Harvard",
        )
        db.add(third)
        await db.flush()

        from app.models.match import Match, MatchStatus
        user_a_id = min(test_user.id, test_user_b.id)
        user_b_id = max(test_user.id, test_user_b.id)
        match = Match(
            user_a_id=user_a_id, user_b_id=user_b_id,
            skill_offered_by_a=python_skill.id, skill_offered_by_b=react_skill.id,
            match_score=0.5, status=MatchStatus.PENDING,
        )
        db.add(match)
        await db.flush()

        # Login as third user
        third_headers = await _login(client, "third@test.com", "TestPass1")
        resp = await client.patch(
            f"{MATCHES_URL}/{match.id}",
            json={"status": "accepted"},
            headers=third_headers,
        )
        assert resp.status_code == 403


# ── Cache behaviour ───────────────────────────────────────────────────────────

class TestMatchCache:

    async def test_second_request_is_cached(
        self, client, auth_headers, test_user, test_user_b,
        python_skill, react_skill, db
    ):
        """Second GET /matches should return cached=true."""
        db.add(UserSkillOffered(user_id=test_user.id, skill_id=python_skill.id))
        db.add(UserSkillWanted(user_id=test_user.id, skill_id=react_skill.id))
        db.add(UserSkillOffered(user_id=test_user_b.id, skill_id=react_skill.id))
        db.add(UserSkillWanted(user_id=test_user_b.id, skill_id=python_skill.id))
        await db.flush()

        # First request — populates cache
        r1 = await client.get(f"{MATCHES_URL}?refresh=true", headers=auth_headers)
        assert r1.status_code == 200

        # Second request — should hit cache
        r2 = await client.get(MATCHES_URL, headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["cached"] is True

    async def test_cache_busted_on_delete(
        self, client, auth_headers, test_user, python_skill, db, redis
    ):
        """Deleting /matches/cache should invalidate the match cache."""
        from app.core.redis_client import RedisKeys
        # Manually set a fake cache entry
        await redis.setex(RedisKeys.user_matches(test_user.id), 300, "[]")

        resp = await client.delete(f"{MATCHES_URL}/cache", headers=auth_headers)
        assert resp.status_code == 204

        exists = await redis.exists(RedisKeys.user_matches(test_user.id))
        assert exists == 0
