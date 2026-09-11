from celery import Celery
from app.config import settings

celery_app = Celery(
    "leadforge",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

import app.workers.tasks  # Load tasks
