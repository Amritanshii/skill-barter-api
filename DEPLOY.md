# Deploying SkillBarter to Render

## What gets deployed
| Service | Type | Notes |
|---------|------|-------|
| `skillbarter-api` | Docker web service | FastAPI + Uvicorn |
| `skillbarter-frontend` | Static site | React + Vite |
| `skillbarter-db` | PostgreSQL | Free tier |
| `skillbarter-redis` | Redis | Free tier |

---

## One-click deploy (Blueprint)

1. Push this repo to GitHub (if not already there)
2. Go to [render.com](https://render.com) → **New** → **Blueprint**
3. Connect your GitHub repo
4. Render reads `render.yaml` automatically and provisions all 4 services
5. Click **Apply** — everything spins up in ~5 minutes

---

## After deployment: 2 manual steps

### Step 1 — Update CORS origins
Once the API and frontend are deployed, you'll have URLs like:
- API: `https://skillbarter-api.onrender.com`
- Frontend: `https://skillbarter-frontend.onrender.com`

In the Render dashboard → **skillbarter-api** → **Environment** → add:
```
CORS_ORIGINS = https://skillbarter-frontend.onrender.com
```

### Step 2 — Run database migrations + seed
In Render dashboard → **skillbarter-api** → **Shell** (or use one-off jobs):
```bash
alembic upgrade head
python scripts/seed_data.py
```

---

## Running locally

```bash
# Terminal 1 — API + DB + Redis (Docker)
docker compose up -d

# Terminal 2 — Frontend
cd frontend
npm install --include=dev
npm run dev
```

- API: http://localhost:8000
- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

---

## Environment variables reference

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | 32+ char random string (`openssl rand -hex 32`) |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | Yes | `redis://host:port/0` |
| `CORS_ORIGINS` | Yes (prod) | Comma-separated allowed frontend URLs |
| `APP_ENV` | No | `development` or `production` (default: development) |
| `VITE_API_URL` | Frontend | Full URL of the API (default: http://localhost:8000) |
