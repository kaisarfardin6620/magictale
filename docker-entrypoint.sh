#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Waiting for PostgreSQL..."
while ! pg_isready -h postgres-db -U "$POSTGSRES_USER" -d "$POSTGRES_DB" -q; do
  sleep 1
done
echo "PostgreSQL started"

# This script runs as root, so we can fix permissions.
# Take ownership of the volume directories so the non-root 'appuser' can write to them.
echo "Setting permissions for media and static folders..."
chown -R appuser:appuser /app/media /app/staticfiles

# From here on, execute commands as the non-root 'appuser'
echo "Applying database migrations as appuser..."
gosu appuser python manage.py migrate

echo "Collecting static files as appuser..."
gosu appuser python manage.py collectstatic --noinput

# Execute the main command (passed from docker-compose) as 'appuser'
echo "Starting application as appuser..."
exec gosu appuser "$@"