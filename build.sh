cat <<EOF > magictale/local_settings.py



import os

CELERY_BROKER_URL = os.getenv("REDIS_URL")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL")
FIREBASE_CREDENTIALS_JSON_STR = os.getenv("FIREBASE_CREDENTIALS_JSON")
EOF