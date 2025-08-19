#!/bin/bash
set -o errexit

pip install -r requirements.txt

# Generate local_settings.py dynamically
cat <<EOF > magictale/local_settings.py
import os
CELERY_BROKER_URL = os.getenv("REDIS_URL")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL")
FIREBASE_CREDENTIALS_JSON_STR = os.getenv("FIREBASE_CREDENTIALS_JSON")
EOF

python manage.py collectstatic --no-input
python manage.py migrate --no-input
