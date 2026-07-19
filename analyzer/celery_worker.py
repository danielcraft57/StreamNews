"""
Point d'entree Celery (compat) :

  celery -A celery_worker worker -Q crawl,ingest,default --concurrency=1

Enregistre le pipeline (crawl -> fan-out ingest -> finalize).
"""
from celery_app import celery_app
import tasks  # noqa: F401  register tasks

from tasks import (  # noqa: E402
    analyze_site_task,
    cleanup_old_analyses,
    crawl_site_task,
    ingest_feed_task,
    finalize_analysis_task,
)

__all__ = [
    "celery_app",
    "analyze_site_task",
    "cleanup_old_analyses",
    "crawl_site_task",
    "ingest_feed_task",
    "finalize_analysis_task",
]

if __name__ == "__main__":
    celery_app.start()
