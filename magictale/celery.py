# magictale_project/celery.py

import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
# Replace 'magictale_project.settings' with 'your_project_name.settings'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magictale_project.settings')

# Create a Celery instance and configure it using the settings from Django.
# The first argument 'magictale_project' is the name of the current module.
app = Celery('magictale_project')

# This line loads the Celery configuration from your Django settings.py file.
# All your Celery settings will be prefixed with 'CELERY_'.
app.config_from_object('django.conf:settings', namespace='CELERY')

# This line automatically discovers task modules in all registered Django apps.
# It will find the 'tasks.py' file you created in your 'ai' app.
app.autodiscover_tasks()