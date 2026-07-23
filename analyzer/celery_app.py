"""Celery app unique + queues specialisees crawl / ingest."""
import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Intervalle rechargement RSS (minutes). Defaut 15 = quasi temps reel pour un flux.
FEED_REFRESH_MINUTES = max(5, min(int(os.getenv("FEED_REFRESH_MINUTES", "15") or 15), 180))

celery_app = Celery("streamnews")
celery_app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_default_queue="default",
    task_routes={
        "streamnews.crawl_site": {"queue": "crawl"},
        "streamnews.ingest_feed": {"queue": "ingest"},
        "streamnews.enrich_article": {"queue": "ingest"},
        "streamnews.enrich_site_articles": {"queue": "ingest"},
        "streamnews.finalize_analysis": {"queue": "default"},
        "streamnews.refresh_daily_brief": {"queue": "default"},
        "streamnews.refresh_all_feeds": {"queue": "default"},
        # compat anciens noms
        "celery_worker.analyze_site_task": {"queue": "crawl"},
        "celery_worker.cleanup_old_analyses": {"queue": "default"},
    },
    beat_schedule={
        "daily-brief-0600-utc": {
            "task": "streamnews.refresh_daily_brief",
            "schedule": crontab(hour=6, minute=0),
        },
        "refresh-all-feeds": {
            "task": "streamnews.refresh_all_feeds",
            "schedule": timedelta(minutes=FEED_REFRESH_MINUTES),
        },
    },
)
