from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StoryProjectViewSet

router = DefaultRouter()
router.register(r"stories", StoryProjectViewSet, basename="stories")

urlpatterns = [
    path("", include(router.urls)),
]