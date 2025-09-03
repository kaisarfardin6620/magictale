# magictale/asgi.py

import os
from django.core.asgi import get_asgi_application

# Set the settings module BEFORE importing anything else from Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magictale.settings')

# Initialize Django's ASGI application early to ensure the app registry is populated.
django_asgi_app = get_asgi_application()

# Now, it is safe to import Channels and other components that might
# rely on Django's models or settings.
from channels.routing import ProtocolTypeRouter, URLRouter
from ai.middleware import JWTAuthMiddleware
import ai.routing

application = ProtocolTypeRouter({
    # Django's ASGI application to handle standard HTTP requests
    "http": django_asgi_app,

    # WebSocket handler
    "websocket": JWTAuthMiddleware(
        URLRouter(
            ai.routing.websocket_urlpatterns
        )
    ),
})