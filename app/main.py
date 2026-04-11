"""
FastAPI application factory.

This module creates and configures the FastAPI app instance.
Everything is wired here: middleware, routers, lifespan, exception handlers.

Why a factory pattern (create_app)?
  - Testable: tests can call create_app() with test config instead of
    importing a module-level 'app' that starts side effects on import.
  - Clean: the factory is the single place that knows about ALL the
    app's cross-cutting concerns (CORS, rate limiting, logging, etc.)

Middleware order matters (innermost applied last):
  Request  → RateLimit → RequestID → Logging → CORS → Route Handler
  Response ← RateLimit ← RequestID ← Logging ← CORS ← Route Handler
"""

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.core.logging import setup_logging
from app.core.redis_client import check_redis_connection, close_redis_pool
from app.database import check_db_connection, close_db, init_db

logger = structlog.get_logger(__name__)
settings = get_settings()


# ── Rate Limiter ──────────────────────────────────────────────────────────────

# Global Limiter instance used as FastAPI state + decorator
# get_remote_address extracts the client IP — slowapi's default key function.
# For user-based limiting, we override the key in individual routers.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    storage_uri=settings.REDIS_URL,   # store counters in Redis
)


# ── Lifespan (startup + shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Async context manager for app startup and shutdown.
    FastAPI 0.93+ recommends lifespan over @app.on_event decorators.

    Startup:
      1. Configure structured logging
      2. Verify PostgreSQL is reachable
      3. (Redis pool is created lazily — no explicit startup needed)

    Shutdown:
      1. Close DB connection pool
      2. Close Redis connection pool
    """
    # ── STARTUP ───────────────────────────────────────────────────────────────
    setup_logging()
    logger.info(
        "app_starting",
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        env=settings.APP_ENV,
    )
    await init_db()
    logger.info("app_ready")

    yield   # Application runs here

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    logger.info("app_shutting_down")
    await close_db()
    await close_redis_pool()
    logger.info("app_stopped")


# ── Application Factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Build and return the configured FastAPI application.
    Called once at module level (see bottom of file).
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "A bidirectional skill-exchange platform for college students.\n\n"
            "Match with peers who offer what you want to learn and want what you can teach."
        ),
        docs_url="/docs" if not settings.is_production else None,   # hide Swagger in prod
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Rate limiter state ────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS Middleware ───────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request ID + Logging Middleware ───────────────────────────────────────
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next) -> Response:
        """
        Attach a unique request_id to every request for distributed tracing.
        Logs request start and end with timing.
        """
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()

        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        # Add request_id to response headers for client-side debugging
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Routers ───────────────────────────────────────────────────────────────
    # Import here (not at top) to avoid circular import issues.
    from app.routers import auth, matches, search, skills, users

    API_PREFIX = "/api/v1"

    app.include_router(auth.router,    prefix=f"{API_PREFIX}/auth",    tags=["Authentication"])
    app.include_router(users.router,   prefix=f"{API_PREFIX}/users",   tags=["Users & Skills"])
    app.include_router(skills.router,  prefix=f"{API_PREFIX}/skills",  tags=["Skill Catalogue"])
    app.include_router(matches.router, prefix=f"{API_PREFIX}/matches", tags=["Matching"])
    app.include_router(search.router,  prefix=f"{API_PREFIX}/search",  tags=["Search"])

    # ── Health check endpoint ─────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], summary="Service health check")
    async def health_check():
        """
        Returns 200 if the service is healthy, 503 if any dependency is down.
        Used by Railway/Render for zero-downtime deployments and monitoring.
        """
        db_ok = await check_db_connection()
        redis_ok = await check_redis_connection()

        status_code = status.HTTP_200_OK if (db_ok and redis_ok) else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if (db_ok and redis_ok) else "degraded",
                "version": settings.APP_VERSION,
                "dependencies": {
                    "postgresql": "ok" if db_ok else "unreachable",
                    "redis": "ok" if redis_ok else "unreachable",
                },
            },
        )

    # ── Root endpoint ─────────────────────────────────────────────────────────
    @app.get("/", tags=["Root"], include_in_schema=False)
    async def root():
        return {
            "message": f"Welcome to {settings.APP_NAME} v{settings.APP_VERSION}",
            "docs": "/docs",
            "health": "/health",
        }

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all for unhandled exceptions.
        Logs the full traceback but returns a generic message to the client
        (never expose internal error details in production).
        """
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. Our team has been notified."},
        )

    return app


# ── Module-level app instance ─────────────────────────────────────────────────
# Uvicorn imports this: uvicorn app.main:app
app = create_app()
