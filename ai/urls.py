# ai/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StoryProjectViewSet # <-- GalleryStoryViewSet removed

router = DefaultRouter()
router.register(r"stories", StoryProjectViewSet, basename="stories")
# The router registration for "gallery" has been removed.

urlpatterns = [
    path("", include(router.urls)),
]