#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Execute the main command (passed from docker-compose)
exec "$@"