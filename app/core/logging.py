"""
Structured logging setup using structlog.

Why structlog over Python's built-in logging?
  - Outputs JSON in production → queryable in cloud logging tools (Datadog,
    CloudWatch, Railway logs).
  - Outputs human-readable coloured text in development.
  - Context variables (request_id, user_id) are automatically attached to
    every log line within a request — no manual passing needed.
  - Processors pipeline: each log event passes through a chain of processors
    that can add timestamps, redact secrets, add context, etc.

Usage:
    import structlog
    logger = structlog.get_logger(__name__)

    logger.info("user_registered", user_id=user.id, email=user.email)
    logger.error("match_engine_failed", user_id=uid, error=str(exc))
    logger.debug("cache_hit", key=cache_key, ttl_remaining=ttl)

In development this renders as:
    2024-01-15 10:30:00 [info     ] user_registered  [app.routers.auth] user_id=abc email=alice@mit.edu

In production (JSON):
    {"event": "user_registered", "user_id": "abc", "email": "alice@mit.edu",
     "timestamp": "2024-01-15T10:30:00Z", "level": "info", "logger": "app.routers.auth"}
"""

import logging
import sys

import structlog
from structlog.types import EventDict, Processor

from app.config import get_settings


def _add_log_level(logger: logging.Logger, method: str, event_dict: EventDict) -> EventDict:
    """Processor: add the log level name to every event."""
    event_dict["level"] = method
    return event_dict


def _drop_color_message_key(logger: logging.Logger, method: str, event_dict: EventDict) -> EventDict:
    """
    Processor: remove Uvicorn's 'color_message' key.
    Uvicorn adds this for terminal coloring; it clutters JSON logs.
    """
    event_dict.pop("color_message", None)
    return event_dict


def setup_logging() -> None:
    """
    Configure structlog and Python's standard logging.
    Called once at application startup in main.py.

    The processor chain:
      1. Add log level name
      2. Add logger name (module path)
      3. Add timestamp (ISO 8601 UTC)
      4. Add call site info (file + line number) in debug mode
      5. Drop Uvicorn color noise
      6. Render: JSON in production, pretty-printed in dev
    """
    settings = get_settings()

    # Map string log level to stdlib constant
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,   # attach request context vars
        _add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _drop_color_message_key,
    ]

    if settings.is_development:
        # Pretty, coloured output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON output for production log aggregators
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Apply to root logger so uvicorn/sqlalchemy logs also go through structlog
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Suppress noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        level = logging.DEBUG if settings.DEBUG else logging.WARNING
        logging.getLogger(noisy).setLevel(level)


def get_request_logger(request_id: str, user_id: str | None = None):
    """
    Create a logger pre-bound with request context.
    Called in the request middleware so all logs within a request
    automatically include the request_id and user_id.

    Usage in middleware:
        log = get_request_logger(request_id=req_id, user_id=uid)
        log.info("request_started", path=request.url.path, method=request.method)
    """
    return structlog.get_logger().bind(
        request_id=request_id,
        user_id=user_id or "anonymous",
    )
