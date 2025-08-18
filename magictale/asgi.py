import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import ai.routing

# === FIX: The original file had a typo in the class name ===
# It was trying to import 'TokenAuthMiddleware', but the class is named 'JWTAuthMiddleware'.
from ai.middleware import JWTAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magictale.settings')

# Get the standard Django HTTP application
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(  # <-- FIX: Use the correct class name here as well
        URLRouter(
            ai.routing.websocket_urlpatterns
        )
    ),
})