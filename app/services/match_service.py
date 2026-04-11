"""
Match service — the core matching engine.

Two-path architecture:
  FAST PATH  (Redis):  sub-5ms  — used when Redis indexes are warm
  SLOW PATH  (SQL):   ~50-80ms  — used on cache miss, rebuilds Redis indexes

The algorithm (bidirectional set intersection):
  For user A, find all users B where:
    B.offered_skills ∩ A.wanted_skills ≠ ∅   (B has what A wants)
    A.offered_skills ∩ B.wanted_skills ≠ ∅   (A has what B wants)

Redis approach (FAST PATH):
  1. SUNIONSTORE tmp_candidates:   union of skill:{sid}:offered_by for each sid in A.wanted
  2. SUNIONSTORE tmp_want_mine:     union of skill:{sid}:wanted_by  for each sid in A.offered
  3. SINTER the two temp sets      → bidirectional matches
  4. Cache result as user:{uid}:matches  TTL=5min

SQL approach (SLOW PATH):
  Two-join query with IN-subqueries + match score calculation.
  After SQL run, rebuilds all Redis indexes so next call hits fast path.

Match score formula:
  score = (|B.offered ∩ A.wanted| + |A.offered ∩ B.wanted|) / (|A.wanted| + |B.wanted|)
  Range: 0.0 → 1.0
"""

import json
from dataclasses import dataclass
from typing import Optional

import structlog
from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import and_, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.redis_client import RedisKeys
from app.models.match import Match, MatchStatus
from app.models.skill import Skill
from app.models.user import User
from app.models.user_skill import UserSkillOffered, UserSkillWanted

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class RawMatchResult:
    """Intermediate representation before ORM serialisation."""
    other_user_id: str
    skill_i_offer_id: str    # skill A offers that B wants
    skill_they_offer_id: str # skill B offers that A wants
    match_score: float


class MatchService:

    # ── Public: get matches for user ─────────────────────────────────────────

    @staticmethod
    async def get_matches(
        db: AsyncSession,
        redis: Redis,
        current_user: User,
        force_refresh: bool = False,
    ) -> list[dict]:
        """
        Return matches for the current user, sorted by match_score descending.

        Tries Redis cache first (fast path).
        Falls back to SQL matching engine (slow path) and repopulates cache.

        Returns a list of dicts shaped for MatchPublic serialisation.
        """
        uid = current_user.id

        if not force_refresh:
            cached = await redis.get(RedisKeys.user_matches(uid))
            if cached:
                logger.debug("match_cache_hit", user_id=uid)
                return json.loads(cached)

        logger.info("match_cache_miss_computing", user_id=uid)

        # Try Redis fast path if indexes are warm
        redis_result = await MatchService._fast_path_redis(redis, uid)

        if redis_result is not None:
            matched_user_ids = redis_result
            raw_matches = await MatchService._enrich_from_db(db, uid, matched_user_ids)
        else:
            # Full SQL matching
            raw_matches = await MatchService._slow_path_sql(db, uid)
            # Rebuild Redis indexes from DB
            await MatchService._rebuild_redis_indexes(db, redis, uid)

        # Persist new matches to the matches table
        await MatchService._upsert_matches(db, uid, raw_matches)
        await db.flush()  # ensure IDs are assigned before serialisation

        # Serialise for cache
        serialised = await MatchService._serialise_matches(db, uid, raw_matches)

        # Cache result
        await redis.setex(
            RedisKeys.user_matches(uid),
            settings.MATCH_CACHE_TTL,
            json.dumps(serialised),
        )

        return serialised

    # ── Fast path: Redis set intersection ────────────────────────────────────

    @staticmethod
    async def _fast_path_redis(
        redis: Redis,
        user_id: str,
    ) -> Optional[list[str]]:
        """
        Use Redis SUNIONSTORE + SINTER to find matching user IDs.
        Returns None if Redis indexes are not populated (cold start).

        Steps:
          1. Get A's wanted skills → [s1, s2]
          2. SUNIONSTORE tmp_candidates ← UNION of skill:s1:offered_by, skill:s2:offered_by
          3. Get A's offered skills → [s3, s4]
          4. SUNIONSTORE tmp_want_mine ← UNION of skill:s3:wanted_by, skill:s4:wanted_by
          5. SINTER tmp_candidates tmp_want_mine → mutual matches
          6. DEL temp keys
        """
        wanted_ids = await redis.smembers(RedisKeys.user_wanted_skills(user_id))
        offered_ids = await redis.smembers(RedisKeys.user_offered_skills(user_id))

        # If keys don't exist, smembers returns empty set — treat as cold cache
        if not wanted_ids and not offered_ids:
            return None

        tmp_candidates = RedisKeys.tmp_candidates(user_id)
        tmp_want_mine = RedisKeys.tmp_want_what_i_offer(user_id)

        pipe = redis.pipeline()

        # Candidates: users who offer what I want
        if wanted_ids:
            offered_by_keys = [RedisKeys.skill_offered_by(sid) for sid in wanted_ids]
            pipe.sunionstore(tmp_candidates, *offered_by_keys)
            pipe.expire(tmp_candidates, 30)  # temp key, 30s TTL
        else:
            pipe.delete(tmp_candidates)

        # Want-mine: users who want what I offer
        if offered_ids:
            wanted_by_keys = [RedisKeys.skill_wanted_by(sid) for sid in offered_ids]
            pipe.sunionstore(tmp_want_mine, *wanted_by_keys)
            pipe.expire(tmp_want_mine, 30)
        else:
            pipe.delete(tmp_want_mine)

        await pipe.execute()

        # Bidirectional intersection
        if not wanted_ids or not offered_ids:
            matched = set()
        else:
            matched = await redis.sinter(tmp_candidates, tmp_want_mine)

        # Clean up temp keys
        await redis.delete(tmp_candidates, tmp_want_mine)

        # Remove self from results
        matched.discard(user_id)

        logger.debug("redis_fast_path", user_id=user_id, match_count=len(matched))
        return list(matched)

    # ── Slow path: SQL bidirectional join ─────────────────────────────────────

    @staticmethod
    async def _slow_path_sql(
        db: AsyncSession,
        user_id: str,
    ) -> list[RawMatchResult]:
        """
        Full SQL matching query.

        Logic:
          Find users B such that:
            B offers at least one skill in A's wanted list (JOIN 1)
            B wants at least one skill in A's offered list (JOIN 2)

          Also compute match_score = (overlap count A→B + overlap count B→A)
                                   / (len(A.wanted) + len(B.wanted))
        """
        # Subquery: skills A wants
        a_wanted = (
            select(UserSkillWanted.skill_id)
            .where(UserSkillWanted.user_id == user_id)
            .scalar_subquery()
        )
        # Subquery: skills A offers
        a_offered = (
            select(UserSkillOffered.skill_id)
            .where(UserSkillOffered.user_id == user_id)
            .scalar_subquery()
        )

        # Count of skills B offers that A wants
        b_offers_a_wants = (
            select(func.count(distinct(UserSkillOffered.skill_id)))
            .where(
                UserSkillOffered.user_id == User.id,
                UserSkillOffered.skill_id.in_(a_wanted),
            )
            .correlate(User)
            .scalar_subquery()
        )
        # Count of skills B wants that A offers
        b_wants_a_offers = (
            select(func.count(distinct(UserSkillWanted.skill_id)))
            .where(
                UserSkillWanted.user_id == User.id,
                UserSkillWanted.skill_id.in_(a_offered),
            )
            .correlate(User)
            .scalar_subquery()
        )
        # Total skills B wants (for normalisation)
        b_total_wanted = (
            select(func.count(distinct(UserSkillWanted.skill_id)))
            .where(UserSkillWanted.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        # Total skills A wants
        a_total_wanted_count = (
            select(func.count(UserSkillWanted.skill_id))
            .where(UserSkillWanted.user_id == user_id)
            .scalar_subquery()
        )

        # Primary offered skill from B that A wants (highest proficiency, take first)
        b_primary_offered = (
            select(UserSkillOffered.skill_id)
            .where(
                UserSkillOffered.user_id == User.id,
                UserSkillOffered.skill_id.in_(a_wanted),
            )
            .order_by(UserSkillOffered.proficiency_level.desc())
            .limit(1)
            .correlate(User)
            .scalar_subquery()
        )
        # Primary offered skill from A that B wants (highest proficiency, take first)
        a_primary_offered_for_b = (
            select(UserSkillOffered.skill_id)
            .where(
                UserSkillOffered.user_id == user_id,
                UserSkillOffered.skill_id.in_(
                    select(UserSkillWanted.skill_id)
                    .where(UserSkillWanted.user_id == User.id)
                ),
            )
            .order_by(UserSkillOffered.proficiency_level.desc())
            .limit(1)
            .correlate(User)
            .scalar_subquery()
        )

        query = (
            select(
                User.id.label("other_user_id"),
                b_primary_offered.label("skill_they_offer_id"),
                a_primary_offered_for_b.label("skill_i_offer_id"),
                (
                    (b_offers_a_wants + b_wants_a_offers).cast(float)
                    / func.nullif(a_total_wanted_count + b_total_wanted, 0)
                ).label("match_score"),
            )
            .where(
                User.id != user_id,
                User.is_active == True,
                b_offers_a_wants > 0,   # B must offer something A wants
                b_wants_a_offers > 0,   # B must want something A offers
            )
            .order_by(text("match_score DESC"))
            .limit(50)
        )

        result = await db.execute(query)
        rows = result.fetchall()

        raw = [
            RawMatchResult(
                other_user_id=row.other_user_id,
                skill_i_offer_id=row.skill_i_offer_id or "",
                skill_they_offer_id=row.skill_they_offer_id or "",
                match_score=float(row.match_score or 0.0),
            )
            for row in rows
            if row.skill_i_offer_id and row.skill_they_offer_id
        ]

        logger.info("sql_slow_path", user_id=user_id, match_count=len(raw))
        return raw

    # ── Enrich Redis fast-path results with SQL details ────────────────────

    @staticmethod
    async def _enrich_from_db(
        db: AsyncSession,
        user_id: str,
        matched_user_ids: list[str],
    ) -> list[RawMatchResult]:
        """
        Given a list of matched user IDs (from Redis), fetch the skill pair
        and score from the DB for each match.
        """
        if not matched_user_ids:
            return []

        results = []
        for other_id in matched_user_ids:
            # Primary skill I offer that they want
            i_offer_res = await db.execute(
                select(UserSkillOffered.skill_id)
                .join(
                    UserSkillWanted,
                    and_(
                        UserSkillWanted.skill_id == UserSkillOffered.skill_id,
                        UserSkillWanted.user_id == other_id,
                    ),
                )
                .where(UserSkillOffered.user_id == user_id)
                .order_by(UserSkillOffered.proficiency_level.desc())
                .limit(1)
            )
            skill_i_offer = i_offer_res.scalar_one_or_none()

            # Primary skill they offer that I want
            they_offer_res = await db.execute(
                select(UserSkillOffered.skill_id)
                .join(
                    UserSkillWanted,
                    and_(
                        UserSkillWanted.skill_id == UserSkillOffered.skill_id,
                        UserSkillWanted.user_id == user_id,
                    ),
                )
                .where(UserSkillOffered.user_id == other_id)
                .order_by(UserSkillOffered.proficiency_level.desc())
                .limit(1)
            )
            skill_they_offer = they_offer_res.scalar_one_or_none()

            if not skill_i_offer or not skill_they_offer:
                continue

            # Simple score: 1 match = 0.5, more overlaps = higher
            score_res = await db.execute(
                select(
                    func.count(distinct(UserSkillOffered.skill_id))
                )
                .where(
                    UserSkillOffered.user_id == other_id,
                    UserSkillOffered.skill_id.in_(
                        select(UserSkillWanted.skill_id)
                        .where(UserSkillWanted.user_id == user_id)
                    ),
                )
            )
            overlap_count = score_res.scalar_one() or 1
            results.append(
                RawMatchResult(
                    other_user_id=other_id,
                    skill_i_offer_id=skill_i_offer,
                    skill_they_offer_id=skill_they_offer,
                    match_score=min(overlap_count / 5.0, 1.0),
                )
            )

        return sorted(results, key=lambda r: r.match_score, reverse=True)

    # ── Upsert matches into the matches table ─────────────────────────────────

    @staticmethod
    async def _upsert_matches(
        db: AsyncSession,
        user_id: str,
        raw_matches: list[RawMatchResult],
    ) -> None:
        """
        Write computed matches to the matches table.
        Uses UPSERT logic: insert new matches, skip existing ones.
        Existing accepted/completed matches are never downgraded.
        """
        for raw in raw_matches:
            other_id = raw.other_user_id
            # Canonical ordering: smaller UUID is always user_a
            user_a_id = min(user_id, other_id)
            user_b_id = max(user_id, other_id)

            existing_res = await db.execute(
                select(Match).where(
                    Match.user_a_id == user_a_id,
                    Match.user_b_id == user_b_id,
                )
            )
            existing = existing_res.scalar_one_or_none()

            if existing:
                # Update score only if it improved
                if raw.match_score > existing.match_score:
                    existing.match_score = raw.match_score
                    db.add(existing)
            else:
                skill_a = raw.skill_i_offer_id if user_a_id == user_id else raw.skill_they_offer_id
                skill_b = raw.skill_they_offer_id if user_a_id == user_id else raw.skill_i_offer_id
                match = Match(
                    user_a_id=user_a_id,
                    user_b_id=user_b_id,
                    skill_offered_by_a=skill_a,
                    skill_offered_by_b=skill_b,
                    match_score=raw.match_score,
                    status=MatchStatus.PENDING,
                    initiated_by=None,
                )
                db.add(match)

    # ── Serialise for cache + API response ────────────────────────────────────

    @staticmethod
    async def _serialise_matches(
        db: AsyncSession,
        user_id: str,
        raw_matches: list[RawMatchResult],
    ) -> list[dict]:
        """
        Build the JSON-serialisable dicts that will be cached in Redis
        and returned directly by the GET /matches endpoint.
        """
        if not raw_matches:
            return []

        # Bulk-fetch match IDs + statuses for all pairs in one query
        from sqlalchemy import or_, and_
        pairs = [(min(user_id, r.other_user_id), max(user_id, r.other_user_id)) for r in raw_matches]
        match_rows = await db.execute(
            select(Match.id, Match.user_a_id, Match.user_b_id, Match.status).where(
                or_(*[and_(Match.user_a_id == a, Match.user_b_id == b) for a, b in pairs])
            )
        )
        match_id_map = {}
        match_status_map = {}
        for m in match_rows.fetchall():
            other = m.user_b_id if m.user_a_id == user_id else m.user_a_id
            match_id_map[other] = str(m.id)
            match_status_map[other] = m.status.value if hasattr(m.status, 'value') else str(m.status)

        serialised = []
        for raw in raw_matches:
            other_user = await db.get(User, raw.other_user_id)
            i_offer_skill = await db.get(Skill, raw.skill_i_offer_id)
            they_offer_skill = await db.get(Skill, raw.skill_they_offer_id)

            if not other_user or not i_offer_skill or not they_offer_skill:
                continue

            serialised.append({
                "match_id": match_id_map.get(raw.other_user_id),
                "match_status": match_status_map.get(raw.other_user_id, "PENDING"),
                "other_user_id": other_user.id,
                "other_username": other_user.username,
                "other_full_name": other_user.full_name,
                "other_college": other_user.college,
                "other_avatar_url": other_user.avatar_url,
                "skill_i_offer_id": i_offer_skill.id,
                "skill_i_offer_name": i_offer_skill.name,
                "skill_i_offer_category": i_offer_skill.category,
                "skill_they_offer_id": they_offer_skill.id,
                "skill_they_offer_name": they_offer_skill.name,
                "skill_they_offer_category": they_offer_skill.category,
                "match_score": round(raw.match_score, 4),
            })

        return serialised

    # ── Rebuild Redis indexes ─────────────────────────────────────────────────

    @staticmethod
    async def _rebuild_redis_indexes(
        db: AsyncSession,
        redis: Redis,
        user_id: str,
    ) -> None:
        """
        After a SQL slow-path run, rebuild the Redis skill-set indexes
        so subsequent calls hit the fast path.
        """
        offered_res = await db.execute(
            select(UserSkillOffered.skill_id).where(UserSkillOffered.user_id == user_id)
        )
        wanted_res = await db.execute(
            select(UserSkillWanted.skill_id).where(UserSkillWanted.user_id == user_id)
        )
        offered_ids = [r[0] for r in offered_res.fetchall()]
        wanted_ids = [r[0] for r in wanted_res.fetchall()]

        pipe = redis.pipeline()
        pipe.delete(RedisKeys.user_offered_skills(user_id))
        pipe.delete(RedisKeys.user_wanted_skills(user_id))
        if offered_ids:
            pipe.sadd(RedisKeys.user_offered_skills(user_id), *offered_ids)
            for sid in offered_ids:
                pipe.sadd(RedisKeys.skill_offered_by(sid), user_id)
        if wanted_ids:
            pipe.sadd(RedisKeys.user_wanted_skills(user_id), *wanted_ids)
            for sid in wanted_ids:
                pipe.sadd(RedisKeys.skill_wanted_by(sid), user_id)
        await pipe.execute()

    # ── Match status update ───────────────────────────────────────────────────

    @staticmethod
    async def update_match_status(
        db: AsyncSession,
        match_id: str,
        current_user_id: str,
        new_status: MatchStatus,
    ) -> Match:
        """
        Accept, reject, or complete a match.

        Business rules:
          - Only participants (user_a or user_b) may update.
          - Valid transitions: pending→accepted, pending→rejected, accepted→completed.
          - Completed/rejected matches are immutable.
        """
        result = await db.execute(select(Match).where(Match.id == match_id))
        match = result.scalar_one_or_none()

        if not match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found.")

        if current_user_id not in (match.user_a_id, match.user_b_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your match.")

        valid_transitions = {
            MatchStatus.PENDING:  {MatchStatus.ACCEPTED, MatchStatus.REJECTED},
            MatchStatus.ACCEPTED: {MatchStatus.COMPLETED},
        }
        allowed = valid_transitions.get(match.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot transition from '{match.status}' to '{new_status}'.",
            )

        match.status = new_status
        if new_status == MatchStatus.ACCEPTED:
            match.initiated_by = current_user_id

        db.add(match)
        logger.info("match_status_updated", match_id=match_id, new_status=new_status)
        return match

    # ── Get single match ──────────────────────────────────────────────────────

    @staticmethod
    async def get_match_by_id(
        db: AsyncSession,
        match_id: str,
        current_user_id: str,
    ) -> Match:
        result = await db.execute(select(Match).where(Match.id == match_id))
        match = result.scalar_one_or_none()

        if not match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found.")
        if current_user_id not in (match.user_a_id, match.user_b_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your match.")

        return match
