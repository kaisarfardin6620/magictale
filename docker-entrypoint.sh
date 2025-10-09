#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Waiting for PostgreSQL..."
while ! pg_isready -h postgres-db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q; do
  sleep 1
done
echo "PostgreSQL started"

echo "Applying database migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Execute the main command (passed from docker-compose)
exec "$@"