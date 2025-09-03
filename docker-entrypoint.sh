#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Wait for the database to be available
echo "Waiting for PostgreSQL..."
while ! pg_isready -h postgres-db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q; do
  sleep 1
done
echo "PostgreSQL started"

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# exec "$@" runs the command passed to the script.
# In this case, it will be the CMD from your Dockerfile:
# ["daphne", "-b", "0.0.0.0", "-p", "8000", "magictale.asgi:application"]
exec "$@"