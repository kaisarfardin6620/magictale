#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

#
# The loop that waited for the local 'postgres-db' container has been removed.
# Your Django application will now connect directly to the remote DATABASE_URL.
#

echo "Applying database migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Execute the main command (passed from docker-compose)
exec "$@"