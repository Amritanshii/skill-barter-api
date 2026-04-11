# ============================================================
# Skill Barter API — Dockerfile
# Multi-stage build for minimal production image size
# ============================================================

# ── Stage 1: Builder ──────────────────────────────────────
# Install dependencies in a separate stage so the final image
# doesn't include build tools (gcc, pip, etc.)
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies (needed to compile bcrypt, asyncpg C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ── Stage 2: Production Image ─────────────────────────────
FROM python:3.11-slim AS production

# Security: run as non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Install runtime-only system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

# Add local bin to PATH so uvicorn is found
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose the port Uvicorn listens on
EXPOSE 8000

# Health check — Docker / Railway uses this to determine container readiness
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start Uvicorn
# --workers: set via WORKERS env var (default 1 for Railway free tier)
# --loop uvloop: faster event loop (installed with uvicorn[standard])
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-1} --loop uvloop"]
