"""
Database seed script — populates the DB with sample data for dev/demo.

Usage:
    python scripts/seed.py

Creates:
  - 30 skills across all categories
  - 5 sample users (Alice, Bob, Carol, Dave, Eve) with offered/wanted skills
  - All Redis indexes synced

Designed for:
  - Local development demos
  - Interview live demos ("let me show you the matching engine")
  - Postman testing

After running:
  - Login as alice@mit.edu / SeedPass1 to see her matches
"""

import asyncio
import sys
import os

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.core.redis_client import get_redis_client
from app.core.security import hash_password
from app.models.skill import Skill
from app.models.user import User
from app.models.user_skill import UserSkillOffered, UserSkillWanted, ProficiencyLevel, UrgencyLevel

SEED_PASSWORD = hash_password("SeedPass1")

SKILLS_DATA = [
    # Programming
    ("Python",       "programming"),
    ("JavaScript",   "programming"),
    ("React",        "programming"),
    ("FastAPI",      "programming"),
    ("SQL",          "programming"),
    ("TypeScript",   "programming"),
    ("Docker",       "programming"),
    ("Git",          "programming"),
    # Design
    ("Figma",        "design"),
    ("Photoshop",    "design"),
    ("UI/UX Design", "design"),
    ("Canva",        "design"),
    # Music
    ("Guitar",       "music"),
    ("Piano",        "music"),
    ("Music Theory", "music"),
    ("Ableton Live", "music"),
    # Languages
    ("Spanish",      "languages"),
    ("French",       "languages"),
    ("Mandarin",     "languages"),
    ("Japanese",     "languages"),
    # Mathematics
    ("Calculus",     "mathematics"),
    ("Linear Algebra","mathematics"),
    ("Statistics",   "mathematics"),
    # Writing
    ("Technical Writing", "writing"),
    ("Copywriting",       "writing"),
    ("Academic Writing",  "writing"),
    # Marketing
    ("SEO",          "marketing"),
    ("Social Media", "marketing"),
    # Finance
    ("Excel",        "finance"),
    ("Financial Modelling", "finance"),
]

USERS_DATA = [
    {
        "email": "alice@mit.edu",
        "username": "alice_codes",
        "full_name": "Alice Smith",
        "college": "MIT",
        "offers": ["Python", "FastAPI", "SQL"],
        "wants":  ["Figma", "UI/UX Design", "React"],
    },
    {
        "email": "bob@stanford.edu",
        "username": "bob_designs",
        "full_name": "Bob Johnson",
        "college": "Stanford",
        "offers": ["Figma", "UI/UX Design", "Photoshop"],
        "wants":  ["Python", "JavaScript", "SQL"],
    },
    {
        "email": "carol@harvard.edu",
        "username": "carol_music",
        "full_name": "Carol Williams",
        "college": "Harvard",
        "offers": ["Guitar", "Piano", "Music Theory"],
        "wants":  ["Spanish", "French", "Technical Writing"],
    },
    {
        "email": "dave@berkeley.edu",
        "username": "dave_words",
        "full_name": "Dave Brown",
        "college": "UC Berkeley",
        "offers": ["Spanish", "French", "Copywriting"],
        "wants":  ["Guitar", "Piano", "Statistics"],
    },
    {
        "email": "eve@cmu.edu",
        "username": "eve_data",
        "full_name": "Eve Davis",
        "college": "CMU",
        "offers": ["Statistics", "Linear Algebra", "Excel"],
        "wants":  ["React", "TypeScript", "Docker"],
    },
]


async def seed():
    print("🌱 Starting seed...")

    async with AsyncSessionLocal() as db:
        redis = get_redis_client()

        # ── Skills ────────────────────────────────────────────────────────
        skill_map: dict[str, Skill] = {}
        print("  Creating skills...")
        for name, category in SKILLS_DATA:
            from sqlalchemy import select
            existing = await db.execute(select(Skill).where(Skill.name == name))
            skill = existing.scalar_one_or_none()
            if not skill:
                skill = Skill(name=name, category=category)
                db.add(skill)
                await db.flush()
                print(f"    + {name} ({category})")
            skill_map[name] = skill

        # ── Users ─────────────────────────────────────────────────────────
        print("  Creating users...")
        for udata in USERS_DATA:
            from sqlalchemy import select
            existing = await db.execute(
                select(User).where(User.email == udata["email"])
            )
            user = existing.scalar_one_or_none()
            if not user:
                user = User(
                    email=udata["email"],
                    username=udata["username"],
                    full_name=udata["full_name"],
                    college=udata["college"],
                    hashed_password=SEED_PASSWORD,
                    is_active=True,
                    is_verified=True,
                )
                db.add(user)
                await db.flush()

            # Offered skills
            for skill_name in udata["offers"]:
                skill = skill_map.get(skill_name)
                if not skill:
                    continue
                ex = await db.execute(
                    select(UserSkillOffered).where(
                        UserSkillOffered.user_id == user.id,
                        UserSkillOffered.skill_id == skill.id,
                    )
                )
                if not ex.scalar_one_or_none():
                    db.add(UserSkillOffered(
                        user_id=user.id,
                        skill_id=skill.id,
                        proficiency_level=ProficiencyLevel.INTERMEDIATE,
                    ))
                    await redis.sadd(f"user:{user.id}:offered_skills", skill.id)
                    await redis.sadd(f"skill:{skill.id}:offered_by", user.id)

            # Wanted skills
            for skill_name in udata["wants"]:
                skill = skill_map.get(skill_name)
                if not skill:
                    continue
                ex = await db.execute(
                    select(UserSkillWanted).where(
                        UserSkillWanted.user_id == user.id,
                        UserSkillWanted.skill_id == skill.id,
                    )
                )
                if not ex.scalar_one_or_none():
                    db.add(UserSkillWanted(
                        user_id=user.id,
                        skill_id=skill.id,
                        urgency=UrgencyLevel.MEDIUM,
                    ))
                    await redis.sadd(f"user:{user.id}:wanted_skills", skill.id)
                    await redis.sadd(f"skill:{skill.id}:wanted_by", user.id)

            print(f"    + {udata['full_name']} ({udata['college']})")

        await db.commit()

    print("\n✅ Seed complete!")
    print("\n📋 Test accounts (password: SeedPass1):")
    for u in USERS_DATA:
        print(f"   {u['email']}")
    print("\n💡 Expected matches:")
    print("   alice ↔ bob   (Python/SQL ↔ Figma/UI-UX)")
    print("   carol ↔ dave  (Guitar/Piano ↔ Spanish/French)")


if __name__ == "__main__":
    asyncio.run(seed())
