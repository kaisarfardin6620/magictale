# ai/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StoryProjectViewSet,
    GalleryStoryViewSet,
    GenerationOptionsView,
)

router = DefaultRouter()
router.register(r"stories", StoryProjectViewSet, basename="stories")
router.register(r"gallery", GalleryStoryViewSet, basename="gallery")

urlpatterns = [
    path("", include(router.urls)),
    path("generation-options/", GenerationOptionsView.as_view(), name="generation-options"),
]