web: daphne -b 0.0.0.0 -p $PORT magictale.asgi:application
worker: DJANGO_SETTINGS_MODULE=magictale.settings celery -A magictale worker -l info