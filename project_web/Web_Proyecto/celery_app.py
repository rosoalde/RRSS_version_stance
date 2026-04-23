from celery import Celery
import os

broker = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
backend = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")

celery_app = Celery(
    "scraper",
    # broker="memory://",
    # backend="cache+memory://"
    broker= broker,#"redis://redis:6379/0",
    backend= backend,#"redis://redis:6379/1"
    #include=["Web_Proyecto.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
