from pathlib import Path
from datetime import timedelta
import environ
import dj_database_url
from django.utils.translation import gettext_lazy as _

env = environ.Env(
    DEBUG=(bool, False)
)
BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(BASE_DIR / '.env')
SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=['http://localhost:3000'])
CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS
CORS_ALLOW_CREDENTIALS = True
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'daphne', 'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'django.contrib.sites', 'corsheaders', 'rest_framework', 'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist', 'channels', 'allauth', 'allauth.account',
    'allauth.socialaccount', 'allauth.socialaccount.providers.google', 'storages',
    'fcm_django', 
    'debug_toolbar',
    'authentication', 'ai', 'subscription', 'support', 'dashboard',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'magictale.api.middleware.APILoggingMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'magictale.urls'
ASGI_APPLICATION = 'magictale.asgi:application'

DATABASES = {'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')}
DATABASES['default']['conn_max_age'] = 600

AUTHENTICATION_BACKENDS = ('django.contrib.auth.backends.ModelBackend', 'allauth.account.auth_backends.AuthenticationBackend',)
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGES = [
    ('en', _('English')), ('es', _('Spanish')), ('fr', _('French')),
    ('de', _('German')), ('it', _('Italian')), ('pt', _('Portuguese')),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

USE_S3_STORAGE = env.bool('USE_S3_STORAGE', default=False)

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if USE_S3_STORAGE:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME')
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug', 'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_RENDERER_CLASSES': ('magictale.api.renderers.CustomJSONRenderer',),
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle', 'rest_framework.throttling.UserRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
        'story_creation': '50/day',
        'login': '5/min',
        'password_reset': '5/hour',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination', 'PAGE_SIZE': 10,
    'EXCEPTION_HANDLER': 'magictale.api.exceptions.custom_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7), 'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True, 'BLACKLIST_AFTER_ROTATION': True,
    'TOKEN_OBTAIN_SERIALIZER': 'authentication.serializers.MyTokenObtainPairSerializer',
    'ALGORITHM': 'HS256', 'SIGNING_KEY': SECRET_KEY,
}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

OPENAI_API_KEY = env("OPENAI_API_KEY", default=None)
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY", default=None)
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
BACKEND_BASE_URL = env('BACKEND_BASE_URL', default='http://127.0.0.1:8001')

REDIS_URL = env("REDIS_URL", default=None)
if REDIS_URL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}
    CELERY_BROKER_URL, CELERY_RESULT_BACKEND = REDIS_URL, REDIS_URL
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache", "LOCATION": f"{REDIS_URL}/1",
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"}
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    CELERY_BROKER_URL, CELERY_RESULT_BACKEND = 'memory://', 'django-db'
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'unique-snowflake-for-magictale'}}

CELERY_ACCEPT_CONTENT, CELERY_TASK_SERIALIZER = ['json'], 'json'
CELERY_RESULT_SERIALIZER, CELERY_TIMEZONE = 'json', 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = 'authentication.adapter.CustomSocialAccountAdapter'
ACCOUNT_EMAIL_VERIFICATION = 'optional'
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {'client_id': env('GOOGLE_CLIENT_ID'), 'secret': env('GOOGLE_CLIENT_SECRET')},
        'SCOPE': ['profile', 'email'], 'AUTH_PARAMS': {'access_type': 'online'}, 'VERIFIED_EMAIL': True,
    }
}
FCM_DJANGO_SETTINGS = {
    "APP_VERBOSE_NAME": "MagicTale",
    "FCM_SERVER_KEY": env('FCM_SERVER_KEY_LEGACY', default=None),
    "ONE_DEVICE_PER_USER": False,
    "DELETE_INACTIVE_DEVICES": True,
    "FCM_CREDENTIALS": env('FIREBASE_SERVICE_ACCOUNT_PATH', default=None),
}
AI_TEXT_MODEL = env("AI_TEXT_MODEL", default="gpt-4-turbo")
AI_IMAGE_MODEL = env("AI_IMAGE_MODEL", default="dall-e-3")
AI_AUDIO_MODEL = env("AI_AUDIO_MODEL", default="tts-1")

ALL_THEMES = ["Space", "Ocean", "Jungle", "City", "Fantasy", "Folktale"]
ALL_ART_STYLES_DATA = {
    "Watercolor Storybook": "style_watercolor.png", "Pixar-like": "style_pixar.png",
    "Anime": "style_anime.png", "Paper-cut": "style_papercut.png",
    "African Folktale": "style_folktale.png", "Clay": "style_clay.png",
}
TIER_1_ART_STYLES = ["Watercolor Storybook", "Pixar-like", "Anime", "Paper-cut", "African Folktale"]
ALL_ART_STYLES = list(ALL_ART_STYLES_DATA.keys())

TIER_1_NARRATOR_VOICES = [
    'EXAVITQu4vr4xnSDxMaL',  
    'IKne3meq5aSn9XLyUdCD',  
    'onwK4e9ZLuTAKqWW03F9',  
]

ALL_NARRATOR_VOICES = [
    '2EiwWnXFnvU5JabPnv8n', 'CwhRBWXzGAHq8TQ4Fs17', 'EXAVITQu4vr4xnSDxMaL',
    'FGY2WhTYpPnrIDTdsKH5', 'IKne3meq5aSn9XLyUdCD', 'JBFqnCBsd6RMkjVDRZzb',
    'N2lVS1w4EtoT3dr4eOWO', 'SAz9YHcvj6GT2YYXdXww', 'SOYHLrjzK2X1ezoPC6cr',
    'TX3LPaxmHKxFdv7VOQHJ', 'Xb7hH8MSUJpSbSDYk0k2', 'XrExE9yKIg1WjnnlVkGX',
    'bIHbv24MWmeRgasZH58o', 'cgSgspJ2msm6clMCkdW9', 'cjVigY5qzO86Huf0OWal',
    'iP95p4xoKVk53GoZ742B', 'nPczCjzI2devNBz1zQrb', 'onwK4e9ZLuTAKqWW03F9',
    'pFZP5JQG7iQjIQuC4Bku', 'pqHfZKP75CvOlQylNhV4'
]

ELEVENLABS_VOICE_MAP = {
    '2EiwWnXFnvU5JabPnv8n': 'Clyde', 'CwhRBWXzGAHq8TQ4Fs17': 'Roger',
    'EXAVITQu4vr4xnSDxMaL': 'Sarah', 'FGY2WhTYpPnrIDTdsKH5': 'Laura',
    'IKne3meq5aSn9XLyUdCD': 'Charlie', 'JBFqnCBsd6RMkjVDRZzb': 'George',
    'N2lVS1w4EtoT3dr4eOWO': 'Callum', 'SAz9YHcvj6GT2YYXdXww': 'River',
    'SOYHLrjzK2X1ezoPC6cr': 'Harry', 'TX3LPaxmHKxFdv7VOQHJ': 'Liam',
    'Xb7hH8MSUJpSbSDYk0k2': 'Alice', 'XrExE9yKIg1WjnnlVkGX': 'Matilda',
    'bIHbv24MWmeRgasZH58o': 'Will', 'cgSgspJ2msm6clMCkdW9': 'Jessica',
    'cjVigY5qzO86Huf0OWal': 'Eric', 'iP95p4xoKVk53GoZ742B': 'Chris',
    'nPczCjzI2devNBz1zQrb': 'Brian', 'onwK4e9ZLuTAKqWW03F9': 'Daniel',
    'pFZP5JQG7iQjIQuC4Bku': 'Lily', 'pqHfZKP75CvOlQylNhV4': 'Bill',
}

INTERNAL_IPS = ["127.0.0.1"]