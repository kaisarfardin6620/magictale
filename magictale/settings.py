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
    'allauth.socialaccount', 
    'allauth.socialaccount.providers.google', 
    'allauth.socialaccount.providers.apple',
    'storages',
    'fcm_django', 
    'debug_toolbar',
    'authentication', 'ai', 'subscription', 'support', 'dashboard','notifications',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'magictale.api.middleware.APILoggingMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'magictale.urls'
ASGI_APPLICATION = 'magictale.asgi:application'

DATABASES = {
    'default': env.db(
        'DATABASE_URL', 
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}'
    )
}

if DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
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
        'login': '5/min',
        'password_reset': '5/hour',
        'story_creation_free': '50/day',
        'story_creation_paid': '10000/day',
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

OPENAI_API_KEY = env("OPENAI_API_KEY")
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY")
BACKEND_BASE_URL = env('BACKEND_BASE_URL', default='http://127.0.0.1:8001')

REVENUECAT_WEBHOOK_AUTH_HEADER = env("REVENUECAT_WEBHOOK_AUTH_HEADER", default=None)

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

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = 'authentication.adapter.CustomSocialAccountAdapter'
ACCOUNT_EMAIL_VERIFICATION = 'optional'

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {'client_id': env('GOOGLE_CLIENT_ID'), 'secret': env('GOOGLE_CLIENT_SECRET')},
        'SCOPE': ['profile', 'email'], 
        'AUTH_PARAMS': {'access_type': 'online'}, 
        'VERIFIED_EMAIL': True,
    },
    'apple': {
        'APP': {
            'client_id': env('APPLE_CLIENT_ID'),
            'secret': env('APPLE_KEY_ID'),
            'key': env('APPLE_KEY_FILE', default=None),
            'certificate_key': env('APPLE_CERTIFICATE_CONTENT', default=None),
            'team_id': env('APPLE_TEAM_ID'),
        },
        'SCOPE': ['email', 'name'],
        'VERIFIED_EMAIL': True,
    }
}

FCM_DJANGO_SETTINGS = {
    "APP_VERBOSE_NAME": "MagicTale",
    "FCM_SERVER_KEY": env('FCM_SERVER_KEY_LEGACY', default=None),
    "ONE_DEVICE_PER_USER": False,
    "DELETE_INACTIVE_DEVICES": True,
    "FCM_CREDENTIALS": env('FIREBASE_SERVICE_ACCOUNT_PATH', default=None),
}
AI_TEXT_MODEL = env("AI_TEXT_MODEL", default="gpt-4o-2024-08-06")
AI_IMAGE_MODEL = env("AI_IMAGE_MODEL", default="dall-e-3")
AI_AUDIO_MODEL = env("AI_AUDIO_MODEL", default="tts-1")

ALL_THEMES_DATA = {
    "space": {"name": "Space Cosmic Adventures", "choices": [
        {"id": "space_1", "name": "Ride a Shooting Star", "description": "Surf through the galaxy and visit a planet made of ice cream.", "image_file": "ride_a_shooting_star.png"},
        {"id": "space_2", "name": "Befriend a Lost Alien", "description": "Help a friendly, four-armed alien fix his spaceship to get home.", "image_file": "befriend_a_lost_alien.png"},
        {"id": "space_3", "name": "Explore a Moon Base", "description": "Bounce in low gravity and discover a garden of glowing moon-flowers.", "image_file": "explore_a_moon_base.png"},
    ]},
    "ocean": {"name": "Ocean Underwater Tales", "choices": [
        {"id": "ocean_1", "name": "Find a Pirate's Treasure", "description": "Follow an old map to a sunken ship guarded by a friendly octopus.", "image_file": "find_a_pirate's_treasure.png"},
        {"id": "ocean_2", "name": "Race a Sea Turtle", "description": "Join a wise old sea turtle on a journey to find the ocean's oldest secret.", "image_file": "race_a_sea_turtle.png"},
        {"id": "ocean_3", "name": "Visit a Mermaid City", "description": "Swim through glowing coral castles and attend a royal mermaid ball.", "image_file": "visit_a_mermaid_city.png"},
    ]},
    "jungle": {"name": "Jungle Wild Explorations", "choices": [
        {"id": "jungle_1", "name": "Discover a Hidden Temple", "description": "Solve ancient puzzles to find what the cheeky monkeys are guarding.", "image_file": "discover_a_hidden_temple.png"},
        {"id": "jungle_2", "name": "Swing with the Monkeys", "description": "Learn to swing from vine to vine with a playful monkey family.", "image_file": "swing_with_the_monkeys.png"},
        {"id": "jungle_3", "name": "Follow a Glowing Butterfly", "description": "Let a magical butterfly lead you to a secret waterfall.", "image_file": "follow_a_glowing_butterfly.png"},
    ]},
    "city": {"name": "City Urban Adventures", "choices": [
        {"id": "city_1", "name": "Drive a Magical Bus", "description": "Become the driver of a special bus that can fly over skyscrapers.", "image_file": "drive_a_magical_bus.png"},
        {"id": "city_2", "name": "Solve a Museum Mystery", "description": "Find out who's been moving the dinosaur bones at night.", "image_file": "solve_a_museum_mystery.png"},
        {"id": "city_3", "name": "Help in a Rooftop Garden", "description": "Meet talking pigeons and grow glowing flowers high above the streets.", "image_file": "help_in_a_rooftop_garden.png"},
    ]},
    "fantasy": {"name": "Fantasy Magical Worlds", "choices": [
        {"id": "fantasy_1", "name": "Hatch a Dragon Egg", "description": "Care for a mysterious, sparkling egg until your very own baby dragon emerges.", "image_file": "hatch_a_dragon_egg.png"},
        {"id": "fantasy_2", "name": "Enter the Magical Castle", "description": "Explore mysterious rooms and meet the friendly dragon guardian.", "image_file": "enter_the_magical_castle.png"},
        {"id": "fantasy_3", "name": "Mix a Potion with a Wizard", "description": "Help a clumsy wizard find the right ingredients for a floating spell.", "image_file": "mix_a_potion_with_a_wizard.png"},
    ]},
    "folktale": {"name": "Folktale Classic Stories", "choices": [
        {"id": "folktale_1", "name": "Help the Three Bears", "description": "Assist Mama, Papa, and Baby Bear in preparing for a surprise forest festival.", "image_file": "help_the_three_bears.png"},
        {"id": "folktale_2", "name": "Outsmart a Gentle Giant", "description": "Use your cleverness to solve a giant's riddles and cross his bridge.", "image_file": "outsmart_a_gentle_giant.png"},
        {"id": "folktale_3", "name": "Visit the Gingerbread House", "description": "Follow a candy trail to a delicious house in the woods for a tea party.", "image_file": "visit_the_gingerbread_house.png"},
    ]},
}

ALL_ART_STYLES_DATA = [
    {"id": "watercolor", "name": "Watercolor Storybook", "description": "soft, dreamy illustrations with flowing colors", "image_file": "style_watercolor.png"},
    {"id": "pixar", "name": "Pixar-like", "description": "3d animated characters with vibrant colors", "image_file": "style_pixar.png"},
    {"id": "anime", "name": "Anime", "description": "japanese animation style with expressive characters", "image_file": "style_anime.png"},
    {"id": "papercut", "name": "Paper-cut", "description": "layered paper artwork with dimensional depth", "image_file": "style_papercut.png"},
    {"id": "african_folktale", "name": "African Folktale", "description": "traditional cultural art with rich patterns", "image_file": "style_folktale.png"},
    {"id": "clay", "name": "Clay", "description": "stop-motion clay figures with texture", "image_file": "style_clay.png"},
]

THEME_ID_TO_NAME_MAP = {theme_id: theme_data['name'] for theme_id, theme_data in ALL_THEMES_DATA.items()}
ART_STYLE_ID_TO_NAME_MAP = {item['id']: item['name'] for item in ALL_ART_STYLES_DATA}

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