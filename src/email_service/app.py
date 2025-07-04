from celery import Celery
import os


redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery('worker', broker=redis_url, backend=redis_url)

celery_app.conf.task_routes = {
    'src.email_service.tasks.send_confirmation_email_task': {'queue': 'email'},
    'src.email_service.tasks.send_password_reset_email_task': {'queue': 'email'},
}