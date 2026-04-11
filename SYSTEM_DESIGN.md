# Skill Barter API — System Design (Step 1)

> Interview-ready system design for a bidirectional skill-exchange platform for college students.

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                               │
│         React SPA / Mobile App / Postman (API testing)              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS (REST + JSON)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        API GATEWAY LAYER                            │
│                                                                     │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │          FastAPI  (Uvicorn ASGI + async/await)               │  │
│   │                                                              │  │
│   │  ┌────────────┐  ┌──────────────┐  ┌─────────────────────┐  │  │
│   │  │ Auth Router│  │ Skills Router│  │  Matches Router     │  │  │
│   │  │ /auth/*    │  │ /skills/*    │  │  /matches/*         │  │  │
│   │  └─────┬──────┘  └──────┬───────┘  └──────────┬──────────┘  │  │
│   │        │                │                      │             │  │
│   │        └────────────────┴──────────────────────┘             │  │
│   │                         │                                    │  │
│   │              ┌──────────▼──────────┐                        │  │
│   │              │   Service Layer     │                        │  │
│   │              │ (Business Logic)    │                        │  │
│   │              └──────────┬──────────┘                        │  │
│   └─────────────────────────┼────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────────┐
              │               │                   │
              ▼               ▼                   ▼
┌─────────────────┐  ┌────────────────┐  ┌───────────────────────┐
│   PostgreSQL    │  │     Redis      │  │   Celery Workers      │
│                 │  │                │  │                       │
│  - Users        │  │  - Match Cache │  │  - Recompute Matches  │
│  - Skills       │  │  - Skill Sets  │  │  - Send Notifications │
│  - Offered      │  │  - Rate Limit  │  │  - Cleanup Jobs       │
│  - Wanted       │  │  - Sessions    │  │                       │
│  - Matches      │  │                │  │  (Broker = Redis)     │
└─────────────────┘  └────────────────┘  └───────────────────────┘
              │               │
              └───────────────┘
                      │
           ┌──────────▼──────────┐
           │   Infrastructure    │
           │  Railway / Render   │
           │  (PostgreSQL addon) │
           │  (Redis addon)      │
           └─────────────────────┘
```

### Data Flow (Request Lifecycle)

```
1. Client sends POST /auth/login
2. FastAPI middleware checks rate limit via Redis
3. Auth service validates credentials against PostgreSQL
4. JWT token issued, stored in Redis (for logout/blacklist support)
5. Client stores token, sends GET /matches with Bearer token
6. JWT middleware validates token
7. Match service checks Redis cache: GET user:{uid}:matches
8.   ├── CACHE HIT  → return cached result (< 1ms)
8.   └── CACHE MISS → run matching engine against PostgreSQL
9.                   → store result in Redis with 5min TTL
10. Response returned to client
11. Celery worker (async) refreshes stale caches in background
```

---

## 2. Database Schema Design

### Entity-Relationship Diagram

```
┌──────────────────────────────────────────┐
│                  users                   │
├──────────────────────────────────────────┤
│ PK  id              UUID                 │
│     email           VARCHAR(255) UNIQUE  │
│     username        VARCHAR(50)  UNIQUE  │
│     hashed_password VARCHAR(255)         │
│     full_name       VARCHAR(255)         │
│     college         VARCHAR(255)         │
│     bio             TEXT                 │
│     avatar_url      VARCHAR(500)         │
│     is_active       BOOLEAN DEFAULT TRUE │
│     is_verified     BOOLEAN DEFAULT FALSE│
│     created_at      TIMESTAMP            │
│     updated_at      TIMESTAMP            │
└──────────────┬──────────────┬────────────┘
               │              │
               │              │
   ┌───────────▼──┐       ┌───▼──────────────┐
   │  user_skills_│       │ user_skills_     │
   │    offered   │       │    wanted        │
   ├──────────────┤       ├──────────────────┤
   │PK id  UUID   │       │PK id  UUID       │
   │FK user_id ──────┐  ┌────── user_id FK   │
   │FK skill_id ─┐   │  │   ┌── skill_id FK  │
   │  proficiency│   │  │   │  urgency       │
   │  description│   │  │   │  description   │
   │  years_exp  │   │  │   │  created_at    │
   │  created_at │   │  │   └────────────────┘
   └─────────────┘   │  │
                     │  │
                     ▼  ▼
┌──────────────────────────────────────────┐
│                  skills                  │
├──────────────────────────────────────────┤
│ PK  id          UUID                     │
│     name        VARCHAR(100) UNIQUE      │
│     category    VARCHAR(50)   INDEXED    │
│     description TEXT                     │
│     created_at  TIMESTAMP                │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                         matches                              │
├──────────────────────────────────────────────────────────────┤
│ PK  id                  UUID                                 │
│ FK  user_a_id           UUID → users.id  INDEXED             │
│ FK  user_b_id           UUID → users.id  INDEXED             │
│ FK  skill_offered_by_a  UUID → skills.id  (A offers → B wants)│
│ FK  skill_offered_by_b  UUID → skills.id  (B offers → A wants)│
│     match_score         FLOAT  (0.0 – 1.0)                  │
│     status              ENUM(pending,accepted,rejected,      │
│                              completed)                      │
│ FK  initiated_by        UUID → users.id                      │
│     created_at          TIMESTAMP                            │
│     updated_at          TIMESTAMP                            │
│ UNIQUE(user_a_id, user_b_id)                                 │
└──────────────────────────────────────────────────────────────┘
```

### Indexes — Why Each One Exists

| Table              | Index Column  | Reason                                              |
|--------------------|---------------|-----------------------------------------------------|
| users              | email         | Login lookup O(log n) instead of full table scan    |
| users              | username      | Profile search                                      |
| skills             | name          | Autocomplete & dedup on skill creation              |
| skills             | category      | Filter skills by category                           |
| user_skills_offered| user_id       | "Show all skills this user offers" — frequent query |
| user_skills_offered| skill_id      | "Who offers Python?" — core matching query          |
| user_skills_wanted | user_id       | "Show what this user wants"                         |
| user_skills_wanted | skill_id      | "Who wants Python?" — core matching query           |
| matches            | user_a_id     | "Show all matches for user"                         |
| matches            | user_b_id     | Same, from the other side                           |
| matches            | (a_id, b_id)  | UNIQUE — prevent duplicate match records            |

---

## 3. Bidirectional Matching Algorithm

### Problem Statement

> Given user **A** who offers skills {X₁, X₂} and wants skills {Y₁, Y₂},  
> find all users **B** such that:
> - **B offers at least one skill A wants** — `B.offered ∩ A.wanted ≠ ∅`
> - **B wants at least one skill A offers** — `B.wanted ∩ A.offered ≠ ∅`

This is a **bidirectional set-intersection problem**.

---

### Algorithm: SQL-Based (Source of Truth)

```sql
-- Find all bidirectional matches for a given user (user_id = :uid)

SELECT
    u.id,
    u.username,
    u.full_name,
    u.college,
    -- Skills B offers that A wants
    ARRAY_AGG(DISTINCT oso.skill_id) FILTER (
        WHERE oso.skill_id IN (
            SELECT skill_id FROM user_skills_wanted WHERE user_id = :uid
        )
    ) AS skills_b_offers_that_a_wants,
    -- Skills A offers that B wants
    ARRAY_AGG(DISTINCT osw.skill_id) FILTER (
        WHERE osw.skill_id IN (
            SELECT skill_id FROM user_skills_offered WHERE user_id = :uid
        )
    ) AS skills_a_offers_that_b_wants,
    -- Match score = (# mutual skills) / (total skills involved)
    (
        COUNT(DISTINCT oso.skill_id) FILTER (
            WHERE oso.skill_id IN (
                SELECT skill_id FROM user_skills_wanted WHERE user_id = :uid
            )
        ) +
        COUNT(DISTINCT osw.skill_id) FILTER (
            WHERE osw.skill_id IN (
                SELECT skill_id FROM user_skills_offered WHERE user_id = :uid
            )
        )
    )::FLOAT AS match_score

FROM users u
-- Condition 1: B offers something A wants
JOIN user_skills_offered oso ON oso.user_id = u.id
    AND oso.skill_id IN (
        SELECT skill_id FROM user_skills_wanted WHERE user_id = :uid
    )
-- Condition 2: B wants something A offers
JOIN user_skills_wanted osw ON osw.user_id = u.id
    AND osw.skill_id IN (
        SELECT skill_id FROM user_skills_offered WHERE user_id = :uid
    )

WHERE u.id != :uid
  AND u.is_active = TRUE
GROUP BY u.id, u.username, u.full_name, u.college
ORDER BY match_score DESC
LIMIT 50;
```

### Algorithm: Redis-Based (Fast Path, < 5ms)

```
Redis Data Structures:

  user:{uid}:offered_skills  →  SET  { skill_id_1, skill_id_2, ... }
  user:{uid}:wanted_skills   →  SET  { skill_id_3, skill_id_4, ... }
  skill:{sid}:offered_by     →  SET  { user_id_A, user_id_C, ... }
  skill:{sid}:wanted_by      →  SET  { user_id_B, user_id_D, ... }

Matching Steps for User A:

  Step 1: Get A's wanted skills
          SMEMBERS user:A:wanted_skills  →  [s1, s2]

  Step 2: Find all users who offer what A wants (candidates)
          SUNIONSTORE tmp:A:candidates
              skill:s1:offered_by
              skill:s2:offered_by
          → {B, C, D, E}

  Step 3: Get A's offered skills
          SMEMBERS user:A:offered_skills  →  [s3, s4]

  Step 4: Find all users who want what A offers
          SUNIONSTORE tmp:A:wants_what_A_offers
              skill:s3:wanted_by
              skill:s4:wanted_by
          → {B, F, G}

  Step 5: Intersect → bidirectional matches!
          SINTER tmp:A:candidates tmp:A:wants_what_A_offers
          → {B}  ← MATCH FOUND

  Step 6: SREM the set to remove A herself
          Cache result: SET user:A:matches "{B}" EX 300

  Step 7: Clean up temp keys
          DEL tmp:A:candidates tmp:A:wants_what_A_offers

Complexity: O(N) where N = total skills across all users
Redis set ops run in microseconds — easily sub-5ms for 10k users
```

### Match Score Formula

```python
match_score = (
    len(B.offered ∩ A.wanted) +   # skills B covers for A
    len(A.offered ∩ B.wanted)     # skills A covers for B
) / (
    len(A.wanted) +               # normalise by total need
    len(B.wanted)
)
# Range: 0.0 (no overlap) → 1.0 (perfect bilateral match)
```

---

## 4. Redis Architecture — How It Improves Performance

### Why Redis?

PostgreSQL set-intersection queries on large datasets require table scans + joins.
Redis native SET data structures do the same in microseconds in memory.

```
PostgreSQL matching query on 100k users:  ~200-400ms  (with indexes: ~50-80ms)
Redis SUNION + SINTER on same data:       ~1-5ms
Speed improvement:                        40x – 400x
```

### Redis Key Design

```
Key Pattern                  Type   TTL      Purpose
────────────────────────────────────────────────────────────────
user:{uid}:offered_skills    SET    No TTL   User's offered skill IDs
user:{uid}:wanted_skills     SET    No TTL   User's wanted skill IDs
user:{uid}:matches           STRING 5 min    Cached match results (JSON)
user:{uid}:profile           HASH   10 min   Cached user profile
skill:{sid}:offered_by       SET    No TTL   Inverted index: who offers this
skill:{sid}:wanted_by        SET    No TTL   Inverted index: who wants this
ratelimit:{uid}:{endpoint}   STRING 1 min    Request counter for rate limiting
blacklist:token:{jti}        STRING JWT exp  Logged-out JWT tokens
```

### Cache Invalidation Strategy

```
Event                        →  Action
─────────────────────────────────────────────────────────────────
User adds offered skill X    →  SADD user:{uid}:offered_skills X
                                SADD skill:X:offered_by uid
                                DEL user:{uid}:matches  (invalidate)

User removes offered skill X →  SREM user:{uid}:offered_skills X
                                SREM skill:X:offered_by uid
                                DEL user:{uid}:matches

User adds wanted skill Y     →  SADD user:{uid}:wanted_skills Y
                                SADD skill:Y:wanted_by uid
                                DEL user:{uid}:matches

Match cache expires (5 min)  →  Celery worker recomputes async
```

---

## 5. Celery Background Jobs

```
Job Name                     Trigger              What It Does
──────────────────────────────────────────────────────────────────
recompute_matches_for_user   Skill add/remove     Updates match cache after
                                                  skill changes (async)

warm_match_cache             Cron: every 5 min    Pre-warms cache for active
                                                  users (those online recently)

send_match_notification      New match found      Notifies users via email/
                                                  push when new match appears

cleanup_expired_matches      Cron: daily          Marks old pending matches
                                                  as expired in DB
```

---

## 6. API Design Overview

```
Auth
  POST   /api/v1/auth/register     Create account
  POST   /api/v1/auth/login        Get JWT token
  POST   /api/v1/auth/logout       Blacklist JWT
  GET    /api/v1/auth/me           Get current user

Skills
  GET    /api/v1/skills            List all skills (paginated, searchable)
  POST   /api/v1/skills            Create a new skill (admin or on-the-fly)

User Profile & Skills
  GET    /api/v1/users/me/profile      Get own profile
  PATCH  /api/v1/users/me/profile      Update profile
  POST   /api/v1/users/me/offered      Add offered skill
  DELETE /api/v1/users/me/offered/{id} Remove offered skill
  POST   /api/v1/users/me/wanted       Add wanted skill
  DELETE /api/v1/users/me/wanted/{id}  Remove wanted skill

Matching
  GET    /api/v1/matches           Get my matches (sorted by score)
  GET    /api/v1/matches/{id}      Get a specific match detail
  PATCH  /api/v1/matches/{id}      Accept / reject a match

Search
  GET    /api/v1/search/users?skill=python&college=MIT   Search users
```

---

## 7. Security Design

```
Layer              Mechanism
─────────────────────────────────────────────────────────────
Authentication     JWT HS256, 30-min access token + 7-day refresh
Password Storage   bcrypt with work factor 12
JWT Blacklisting   Logged-out tokens stored in Redis until expiry
Rate Limiting      Sliding window via Redis: 100 req/min per user
Input Validation   Pydantic v2 strict mode on all request bodies
SQL Injection      SQLAlchemy ORM with parameterised queries only
CORS               Whitelisted origins only in production
HTTPS              Enforced at Railway/Render reverse proxy
```

---

## 8. Performance Targets

| Endpoint            | Target P95 Latency | Strategy                       |
|---------------------|--------------------|--------------------------------|
| GET /matches        | < 10ms             | Redis cache hit                |
| GET /matches (cold) | < 80ms             | PostgreSQL + indexes           |
| POST /auth/login    | < 100ms            | bcrypt + indexed email lookup  |
| GET /search/users   | < 50ms             | PostgreSQL FTS + Redis cache   |
| POST skill update   | < 30ms             | DB write + async cache update  |

---

## 9. Deployment Architecture (Railway/Render)

```
┌─────────────────────────────────────────────────────────┐
│                     Railway / Render                    │
│                                                         │
│  ┌───────────────┐   ┌─────────────┐  ┌─────────────┐  │
│  │  Web Service  │   │  PostgreSQL │  │    Redis    │  │
│  │  FastAPI App  │──▶│  (Managed)  │  │  (Managed)  │  │
│  │  (Uvicorn)    │──▶│             │  │             │  │
│  └───────────────┘   └─────────────┘  └─────────────┘  │
│                                              ▲          │
│  ┌───────────────┐                           │          │
│  │ Worker Service│                           │          │
│  │ Celery Worker │───────────────────────────┘          │
│  │ (same image)  │  (broker + result backend = Redis)   │
│  └───────────────┘                                      │
└─────────────────────────────────────────────────────────┘
```

---

*Step 1 complete. Next: Step 2 — Project Setup & Folder Structure.*
