import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magictale.settings')

app = Celery('magictale') 

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.beat_schedule = {
    'cleanup-stalled-projects-daily': {
        'task': 'ai.tasks.cleanup_stalled_projects_task',
        'schedule': crontab(minute=0, hour=3),
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')