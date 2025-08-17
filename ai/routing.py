from django.urls import re_path
from .consumers import StoryProgressConsumer

websocket_urlpatterns = [
    re_path(r"^ws/ai/stories/(?P<project_id>\d+)/$", StoryProgressConsumer.as_asgi()),
]