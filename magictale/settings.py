from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv
import dj_database_url

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core Security Settings ---
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("A SECRET_KEY must be set in the .env file")
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# --- HOSTING & SECURITY ---
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000').split(',')
CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS # Makes CORS config simpler, uses the same list.
CORS_ALLOW_CREDENTIALS = True
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# --- Application Definition ---
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'channels',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'storages',
    'fcm_django',
    'authentication',
    'ai',
    'subscription',
    'support',
    'dashboard',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware', # Must be high up
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'magictale.urls'
ASGI_APPLICATION = 'magictale.asgi.application'

# --- Database & Auth Backends ---
DATABASES = {'default': dj_database_url.config(default=f'sqlite:///{BASE_DIR / "db.sqlite3"}', conn_max_age=600)}
AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend', 'allauth.account.auth_backends.AuthenticationBackend',)
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE, TIME_ZONE, USE_I18N, USE_TZ = 'en-us', 'UTC', True, True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- MASTER SWITCH FOR CLOUD STORAGE ---
USE_S3_STORAGE = os.getenv('USE_S3_STORAGE', 'False').lower() == 'true'

# --- Static & Media Files ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

if USE_S3_STORAGE:
    # --- S3 Storage Configuration ---
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
else:
    # --- Local Storage Configuration ---
    MEDIA_URL = '/media/'
    MEDIA_ROOT = '/app/media' # More direct path for Docker volume mount

# --- Templates ---
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
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

# --- REST Framework and JWT Settings ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle', 'rest_framework.throttling.UserRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'anon': '100/day', 'user': '1000/day'},
    'DEFAULT_RENDERER_CLASSES': [
        'magictale.api.renderers.CustomJSONRenderer', # Make sure this path is correct for your project
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'EXCEPTION_HANDLER': 'magictale.api.exceptions.custom_exception_handler', # Make sure this path is correct
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
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
EMAIL_HOST, EMAIL_PORT = os.getenv('EMAIL_HOST'), int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER, EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_USER'), os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')

# --- Third-Party API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# --- Channels and Celery ---
REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}
    CELERY_BROKER_URL, CELERY_RESULT_BACKEND = REDIS_URL, REDIS_URL
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CELERY_BROKER_URL, CELERY_RESULT_BACKEND = 'memory://', 'django-db'
CELERY_ACCEPT_CONTENT, CELERY_TASK_SERIALIZER = ['json'], 'json'
CELERY_RESULT_SERIALIZER, CELERY_TIMEZONE = 'json', 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# --- Allauth Configuration ---
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = 'authentication.adapter.CustomSocialAccountAdapter'
ACCOUNT_SIGNUP_FORM_CLASS = None
ACCOUNT_EMAIL_VERIFICATION = 'optional'
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {'client_id': os.getenv('GOOGLE_CLIENT_ID'), 'secret': os.getenv('GOOGLE_CLIENT_SECRET')},
        'SCOPE': ['profile', 'email'], 'AUTH_PARAMS': {'access_type': 'online'}, 'VERIFIED_EMAIL': True,
    }
}

# --- FCM Push Notifications ---
FCM_DJANGO_SETTINGS = {
    "APP_VERBOSE_NAME": "MagicTale",
    "FCM_SERVER_KEY": os.getenv('FCM_SERVER_KEY_LEGACY'),
    "ONE_DEVICE_PER_USER": False,
    "DELETE_INACTIVE_DEVICES": True,
    "FCM_CREDENTIALS": os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH'),
}

# --- AI Model Configuration ---
AI_TEXT_MODEL, AI_IMAGE_MODEL, AI_AUDIO_MODEL = os.getenv("AI_TEXT_MODEL", "gpt-4o-mini"), os.getenv("AI_IMAGE_MODEL", "dall-e-3"), os.getenv("AI_AUDIO_MODEL", "tts-1")


# --- Custom Project Settings ---
BACKEND_BASE_URL = os.getenv('BACKEND_BASE_URL', 'http://127.0.0.1:8001')