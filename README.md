# Skill Barter API

> A production-ready bidirectional skill-exchange platform for college students.
> Built with FastAPI, PostgreSQL, Redis, and Celery.

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-red)](https://redis.io)

---

## What It Does

College students list skills they **offer** and skills they **want** to learn.  
The system automatically finds **bidirectional matches**:

```
Alice offers: Python, SQL       →  Bob offers: Figma, UI/UX
Alice wants:  Figma, UI/UX      →  Bob wants:  Python, SQL
                    ↕ MATCH ↕
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| API | FastAPI + Uvicorn | Async, auto-docs, fast |
| Database | PostgreSQL 16 | ACID, complex joins |
| ORM | SQLAlchemy 2.x async | Type-safe, async-native |
| Cache | Redis 7 | Sub-5ms match queries |
| Background Jobs | Celery + Redis | Non-blocking recompute |
| Auth | JWT (HS256) + bcrypt | Stateless, secure |
| Migrations | Alembic | Version-controlled schema |
| Testing | pytest-asyncio + fakeredis | Fast, isolated tests |
| Deployment | Railway / Render | Zero-config PaaS |

---

## Architecture

```
Client → FastAPI (Uvicorn) → Service Layer
                                  ├── PostgreSQL (source of truth)
                                  └── Redis (match cache + inverted indexes)
                                           ↑
                              Celery Worker (async recompute)
```

**Matching algorithm** — bidirectional set intersection:
- Fast path (Redis `SUNIONSTORE` + `SINTER`): **~2ms**
- Slow path (SQL joins, cache miss): **~60ms**

---

## Quick Start (Docker)

```bash
# 1. Clone and configure
git clone https://github.com/yourusername/skill-barter-api.git
cd skill-barter-api
cp .env.example .env
# Edit .env: set SECRET_KEY=$(openssl rand -hex 32)

# 2. Start everything
docker-compose up -d

# 3. Run migrations
docker-compose exec api alembic upgrade head

# 4. Seed sample data (optional)
docker-compose exec api python scripts/seed.py

# 5. Open API docs
open http://localhost:8000/docs
```

---

## Local Development (without Docker)

```bash
# Prerequisites: Python 3.11+, PostgreSQL, Redis running locally

# 1. Create virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your local DB + Redis credentials

# 4. Run migrations
alembic upgrade head

# 5. Start the API
uvicorn app.main:app --reload --port 8000

# 6. Start Celery worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info

# 7. Start Celery Beat scheduler (separate terminal)
celery -A app.workers.celery_app beat --loglevel=info
```

---

## API Documentation

Interactive docs available at **http://localhost:8000/docs** (development only).

### Authentication

All endpoints (except `/auth/register` and `/auth/login`) require:
```
Authorization: Bearer <access_token>
```

### Endpoints

#### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Login (email or username) |
| POST | `/api/v1/auth/logout` | Blacklist token |
| POST | `/api/v1/auth/refresh` | Rotate tokens |
| GET  | `/api/v1/auth/me` | Current user |

#### Users & Skills
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/v1/users/me/profile` | Full profile + skills |
| PATCH  | `/api/v1/users/me/profile` | Update profile |
| POST   | `/api/v1/users/me/offered` | Add offered skill |
| DELETE | `/api/v1/users/me/offered/{id}` | Remove offered skill |
| POST   | `/api/v1/users/me/wanted` | Add wanted skill |
| DELETE | `/api/v1/users/me/wanted/{id}` | Remove wanted skill |
| GET    | `/api/v1/users/{username}` | Public profile |

#### Skills Catalogue
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/v1/skills` | List all skills (paginated) |
| POST   | `/api/v1/skills` | Create new skill |
| GET    | `/api/v1/skills/autocomplete?q=` | Autocomplete |
| GET    | `/api/v1/skills/{id}` | Get skill by ID |

#### Matching
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/v1/matches` | My matches (cache-first) |
| GET    | `/api/v1/matches/{id}` | Match detail |
| PATCH  | `/api/v1/matches/{id}` | Accept/reject/complete |
| DELETE | `/api/v1/matches/cache` | Force cache refresh |

#### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/v1/search/users?skill=&college=` | Find users by skill/college |
| GET    | `/api/v1/search/skills?q=` | Search skills |

### Example: Register → Add Skills → Get Matches

```bash
# 1. Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@mit.edu","username":"alice","password":"SecurePass1","college":"MIT"}'

# 2. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"alice@mit.edu","password":"SecurePass1"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['tokens']['access_token'])")

# 3. Add Python as an offered skill (get skill_id from /api/v1/skills first)
curl -X POST http://localhost:8000/api/v1/users/me/offered \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"skill_id":"<python-skill-id>","proficiency_level":"expert"}'

# 4. Add React as a wanted skill
curl -X POST http://localhost:8000/api/v1/users/me/wanted \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"skill_id":"<react-skill-id>","urgency":"high"}'

# 5. Get matches
curl http://localhost:8000/api/v1/matches \
  -H "Authorization: Bearer $TOKEN"
```

---

## Running Tests

```bash
# Create test database first
createdb skillbarter_test   # or via psql

# Run all tests
pytest -v

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run a specific file
pytest tests/test_auth.py -v

# Run a specific test
pytest tests/test_matches.py::TestBidirectionalMatching::test_bidirectional_match_found -v
```

---

## Deployment (Railway)

```bash
# 1. Install Railway CLI
npm install -g @railway/cli && railway login

# 2. Create project
railway new

# 3. Add PostgreSQL + Redis plugins in Railway dashboard

# 4. Set environment variables in Railway dashboard:
#    SECRET_KEY      = (openssl rand -hex 32)
#    DATABASE_URL    = (auto-set by Railway PostgreSQL plugin)
#    REDIS_URL       = (auto-set by Railway Redis plugin)
#    APP_ENV         = production
#    DEBUG           = false

# 5. Deploy
railway up

# 6. Run migrations
railway run alembic upgrade head

# 7. Seed data (optional)
railway run python scripts/seed.py
```

**Render deployment** — add a `render.yaml`:
```yaml
services:
  - type: web
    name: skill-barter-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: APP_ENV
        value: production
```

---

## Project Structure

```
skill-barter-api/
├── app/
│   ├── main.py              # FastAPI factory + middleware
│   ├── config.py            # Pydantic Settings (.env loader)
│   ├── database.py          # Async SQLAlchemy engine
│   ├── dependencies.py      # DI: get_db, get_redis, get_current_user
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # FastAPI route handlers
│   ├── services/            # Business logic (auth, users, skills, matches)
│   ├── core/                # Security, Redis client, logging
│   └── workers/             # Celery tasks + beat schedule
├── alembic/                 # DB migrations
├── tests/                   # pytest-asyncio test suite
├── scripts/seed.py          # Dev/demo seed data
├── Dockerfile               # Multi-stage production image
├── docker-compose.yml       # Local dev stack
├── requirements.txt
└── .env.example
```

---

## Key Design Decisions

**Why UUID primary keys?**  
Prevents ID enumeration attacks. Attacker can't guess `user/2` after seeing `user/1`.

**Why async SQLAlchemy?**  
A synchronous DB call blocks the event loop. Async lets FastAPI handle N concurrent requests while waiting for Postgres I/O. At 100 concurrent users with 50ms queries: sync = 5s blocked, async ≈ 50ms total.

**Why two-path matching?**  
SQL gives correct results but takes ~60ms. Redis set intersection (`SUNIONSTORE` + `SINTER`) takes ~2ms. We use Redis as the fast path and fall back to SQL on cache miss, which also rebuilds the Redis indexes automatically.

**Why token blacklisting in Redis?**  
JWTs are stateless — once issued they're valid until expiry. Without a blacklist, a logged-out token remains usable for up to 30 minutes. Redis blacklist adds ~1ms per request but gives real logout security. The blacklist entry auto-expires matching the token TTL, keeping Redis memory bounded.

---

## Health Check

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"1.0.0","dependencies":{"postgresql":"ok","redis":"ok"}}
```

---

## License

MIT
