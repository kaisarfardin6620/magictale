# your_project/settings.py

from pathlib import Path
from datetime import timedelta
import os
import json
import firebase_admin
from firebase_admin import credentials
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core Security Settings ---

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in the .env file")

# DEBUG is True for local development
DEBUG = True

# --- Host and CORS Configuration ---

# Get the Ngrok hostname from your .env file
NGROK_HOSTNAME = os.getenv('NGROK_HOSTNAME')

# Default allowed hosts for local development
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
if NGROK_HOSTNAME:
    print(f"Ngrok development mode enabled for host: {NGROK_HOSTNAME}")
    ALLOWED_HOSTS.append(NGROK_HOSTNAME)

# Trust the Ngrok domain for CSRF POST requests
CSRF_TRUSTED_ORIGINS = []
if NGROK_HOSTNAME:
    # CSRF_TRUSTED_ORIGINS requires the 'https://' scheme
    CSRF_TRUSTED_ORIGINS.append(f'https://{NGROK_HOSTNAME}')

# Allow your frontend and Ngrok to make cross-origin requests
CORS_ALLOWED_ORIGINS = [
    os.getenv('FRONTEND_URL', 'http://localhost:3000'),
]
if NGROK_HOSTNAME:
    # CORS_ALLOWED_ORIGINS also requires the 'https://' scheme
    CORS_ALLOWED_ORIGINS.append(f'https://{NGROK_HOSTNAME}')


# --- Application Definition ---

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'channels',
    'corsheaders',
    'authentication',
    'ai',
    'notification',
    'subscription',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', # Should be high up
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'magictale.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [], 'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
ASGI_APPLICATION = 'magictale.asgi.application'

# --- Database Configuration (Using SQLite3 for local development) ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# --- Password validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization, Static, Media, etc. ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- REST Framework and JWT Settings ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle', 'rest_framework.throttling.UserRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'anon': '100/day', 'user': '1000/day'}
}
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'TOKEN_OBTAIN_SERIALIZER': 'authentication.serializers.MyTokenObtainPairSerializer',
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}

# --- Email Settings ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)

# --- Third-Party API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# --- Channels and Celery ---
REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
else:
    # Fallback for local dev without Docker/Redis running
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'django-db'

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# --- Firebase Initialization ---
try:
    firebase_creds_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_creds_json_str:
        firebase_creds_dict = json.loads(firebase_creds_json_str)
        cred = credentials.Certificate(firebase_creds_dict)
    else:
        cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
        else:
            cred = None
            print("WARNING: Firebase credentials not found.")

    if cred and not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully.")
except Exception as e:
    print(f"CRITICAL ERROR: Could not initialize Firebase Admin SDK: {e}")