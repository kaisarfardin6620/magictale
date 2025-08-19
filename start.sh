#!/bin/bash
export DJANGO_SETTINGS_MODULE=magictale.settings

echo "Starting Celery worker..."
celery -A magictale worker -l info &

echo "Starting Daphne server..."
daphne -b 0.0.0.0 -p $PORT magictale.asgi:application