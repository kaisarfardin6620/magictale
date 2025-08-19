# magictale/celery.py

import os
from celery import Celery

# This line tells Django where your settings are.
# Make sure 'magictale.settings' is the correct path.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magictale.settings')

# THIS IS THE LIKELY FIX: The string 'magictale' here MUST match
# the project name.
app = Celery('magictale') 

# This tells Celery to look for settings starting with 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')

# This finds your tasks.py files.
app.autodiscover_tasks()