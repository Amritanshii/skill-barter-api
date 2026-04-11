"""
Skill catalogue and user-skill management tests.

Covers:
  - Skill CRUD (create, list, get, duplicate check)
  - Add/remove offered skills (DB + Redis sync)
  - Add/remove wanted skills (DB + Redis sync)
  - Validation: non-existent skill, duplicate skill add
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

SKILLS_URL  = "/api/v1/skills"
OFFERED_URL = "/api/v1/users/me/offered"
WANTED_URL  = "/api/v1/users/me/wanted"
PROFILE_URL = "/api/v1/users/me/profile"


# ── Skill Catalogue ───────────────────────────────────────────────────────────

class TestSkillCatalogue:

    async def test_create_skill_success(self, client: AsyncClient, auth_headers):
        resp = await client.post(SKILLS_URL, json={
            "name": "Rust",
            "category": "programming",
            "description": "Systems programming language",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Rust"
        assert data["category"] == "programming"
        assert "id" in data

    async def test_create_skill_duplicate(self, client: AsyncClient, auth_headers, python_skill):
        resp = await client.post(SKILLS_URL, json={
            "name": "Python",   # already exists
            "category": "programming",
        }, headers=auth_headers)
        assert resp.status_code == 409

    async def test_create_skill_invalid_category(self, client: AsyncClient, auth_headers):
        resp = await client.post(SKILLS_URL, json={
            "name": "SomeSkill",
            "category": "invalid_category",
        }, headers=auth_headers)
        assert resp.status_code == 422

    async def test_list_skills(self, client: AsyncClient, auth_headers, python_skill, react_skill):
        resp = await client.get(SKILLS_URL, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 2

    async def test_list_skills_filter_by_category(
        self, client: AsyncClient, auth_headers, python_skill
    ):
        resp = await client.get(
            f"{SKILLS_URL}?category=programming", headers=auth_headers
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["category"] == "programming"

    async def test_list_skills_search(self, client: AsyncClient, auth_headers, python_skill):
        resp = await client.get(
            f"{SKILLS_URL}?search=Py", headers=auth_headers
        )
        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()["items"]]
        assert "Python" in names

    async def test_get_skill_by_id(self, client: AsyncClient, auth_headers, python_skill):
        resp = await client.get(f"{SKILLS_URL}/{python_skill.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Python"

    async def test_get_skill_not_found(self, client: AsyncClient, auth_headers):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(f"{SKILLS_URL}/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_autocomplete(self, client: AsyncClient, auth_headers, python_skill, react_skill):
        resp = await client.get(
            f"{SKILLS_URL}/autocomplete?q=Py", headers=auth_headers
        )
        assert resp.status_code == 200
        names = [s["name"] for s in resp.json()]
        assert "Python" in names
        assert "React" not in names  # "React" doesn't start with "Py"

    async def test_unauthenticated_cannot_list_skills(self, client: AsyncClient):
        resp = await client.get(SKILLS_URL)
        assert resp.status_code == 401


# ── Offered Skills ────────────────────────────────────────────────────────────

class TestOfferedSkills:

    async def test_add_offered_skill_success(
        self, client: AsyncClient, auth_headers, python_skill
    ):
        resp = await client.post(OFFERED_URL, json={
            "skill_id": python_skill.id,
            "proficiency_level": "expert",
            "description": "3 years Django experience",
            "years_experience": 3.0,
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["skill"]["name"] == "Python"
        assert data["proficiency_level"] == "expert"

    async def test_add_offered_skill_nonexistent(
        self, client: AsyncClient, auth_headers
    ):
        resp = await client.post(OFFERED_URL, json={
            "skill_id": "00000000-0000-0000-0000-000000000000",
        }, headers=auth_headers)
        assert resp.status_code == 404

    async def test_add_offered_skill_duplicate(
        self, client: AsyncClient, auth_headers, python_skill
    ):
        # Add once
        await client.post(OFFERED_URL, json={"skill_id": python_skill.id},
                          headers=auth_headers)
        # Add again → 409
        resp = await client.post(OFFERED_URL, json={"skill_id": python_skill.id},
                                 headers=auth_headers)
        assert resp.status_code == 409

    async def test_list_offered_skills(
        self, client: AsyncClient, auth_headers, python_skill
    ):
        await client.post(OFFERED_URL, json={"skill_id": python_skill.id},
                          headers=auth_headers)
        resp = await client.get(OFFERED_URL, headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_remove_offered_skill(
        self, client: AsyncClient, auth_headers, python_skill
    ):
        add_resp = await client.post(
            OFFERED_URL, json={"skill_id": python_skill.id}, headers=auth_headers
        )
        skill_record_id = add_resp.json()["id"]

        del_resp = await client.delete(
            f"{OFFERED_URL}/{skill_record_id}", headers=auth_headers
        )
        assert del_resp.status_code == 204

        # Verify gone
        list_resp = await client.get(OFFERED_URL, headers=auth_headers)
        ids = [s["id"] for s in list_resp.json()]
        assert skill_record_id not in ids

    async def test_remove_offered_skill_wrong_user(
        self, client: AsyncClient, auth_headers, test_user_b,
        python_skill, db: AsyncSession
    ):
        """User B's offered skill cannot be deleted by User A."""
        from app.models.user_skill import UserSkillOffered
        b_skill = UserSkillOffered(
            user_id=test_user_b.id,
            skill_id=python_skill.id,
        )
        db.add(b_skill)
        await db.flush()

        resp = await client.delete(
            f"{OFFERED_URL}/{b_skill.id}", headers=auth_headers
        )
        assert resp.status_code == 404


# ── Wanted Skills ─────────────────────────────────────────────────────────────

class TestWantedSkills:

    async def test_add_wanted_skill_success(
        self, client: AsyncClient, auth_headers, react_skill
    ):
        resp = await client.post(WANTED_URL, json={
            "skill_id": react_skill.id,
            "urgency": "high",
            "description": "Need it for final year project",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["skill"]["name"] == "React"
        assert data["urgency"] == "high"

    async def test_add_wanted_duplicate(
        self, client: AsyncClient, auth_headers, react_skill
    ):
        await client.post(WANTED_URL, json={"skill_id": react_skill.id},
                          headers=auth_headers)
        resp = await client.post(WANTED_URL, json={"skill_id": react_skill.id},
                                 headers=auth_headers)
        assert resp.status_code == 409

    async def test_remove_wanted_skill(
        self, client: AsyncClient, auth_headers, react_skill
    ):
        add_resp = await client.post(
            WANTED_URL, json={"skill_id": react_skill.id}, headers=auth_headers
        )
        record_id = add_resp.json()["id"]

        del_resp = await client.delete(f"{WANTED_URL}/{record_id}", headers=auth_headers)
        assert del_resp.status_code == 204


# ── Redis sync ────────────────────────────────────────────────────────────────

class TestRedisSync:

    async def test_redis_indexes_updated_on_add(
        self, client: AsyncClient, auth_headers, python_skill, redis, test_user
    ):
        """Adding an offered skill should update Redis inverted indexes."""
        from app.core.redis_client import RedisKeys

        await client.post(OFFERED_URL, json={"skill_id": python_skill.id},
                          headers=auth_headers)

        # user's offered skills SET should contain this skill
        members = await redis.smembers(RedisKeys.user_offered_skills(test_user.id))
        assert python_skill.id in members

        # skill's offered_by SET should contain this user
        offerers = await redis.smembers(RedisKeys.skill_offered_by(python_skill.id))
        assert test_user.id in offerers

    async def test_redis_indexes_cleared_on_remove(
        self, client: AsyncClient, auth_headers, python_skill, redis, test_user
    ):
        from app.core.redis_client import RedisKeys

        add_resp = await client.post(
            OFFERED_URL, json={"skill_id": python_skill.id}, headers=auth_headers
        )
        record_id = add_resp.json()["id"]
        await client.delete(f"{OFFERED_URL}/{record_id}", headers=auth_headers)

        members = await redis.smembers(RedisKeys.user_offered_skills(test_user.id))
        assert python_skill.id not in members
