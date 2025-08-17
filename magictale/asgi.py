import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magictale.settings')
django_asgi_app = get_asgi_application()  # Django fully initialized here

from channels.routing import ProtocolTypeRouter, URLRouter
from ai.routing import websocket_urlpatterns
from ai.middleware import TokenAuthMiddleware 

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})