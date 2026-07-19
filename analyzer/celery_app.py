"""Celery app unique + queues specialisees crawl / ingest."""
import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

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
        "streamnews.finalize_analysis": {"queue": "default"},
        # compat anciens noms
        "celery_worker.analyze_site_task": {"queue": "crawl"},
        "celery_worker.cleanup_old_analyses": {"queue": "default"},
    },
)
