"""
Celery application instance with beat (cron) schedule.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "skillbarter",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # fair task distribution
    task_acks_late=True,            # re-queue on worker crash
    result_expires=3600,            # keep results 1 hour
)

# ── Beat schedule (cron jobs) ─────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "warm-match-cache-every-10-min": {
        "task": "tasks.warm_match_cache",
        "schedule": crontab(minute="*/10"),
    },
    "cleanup-expired-matches-daily": {
        "task": "tasks.cleanup_expired_matches",
        "schedule": crontab(hour=2, minute=0),  # 02:00 UTC daily
    },
}
