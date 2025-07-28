import os
from celery import Celery

# Configuration Celery
celery_app = Celery('streamnews_worker')
celery_app.conf.update(
    broker_url=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    result_backend=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000
)

# Import des tâches depuis le service d'analyse
from analyzer.celery_worker import analyze_site_task, cleanup_old_analyses

if __name__ == '__main__':
    celery_app.start() 