from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SubscriptionViewSet
from .webhooks import revenuecat_webhook

router = DefaultRouter()
router.register(r"subscriptions", SubscriptionViewSet, basename="subscriptions")

urlpatterns = [
    path("", include(router.urls)),
    path("webhooks/revenuecat/", revenuecat_webhook, name="revenuecat-webhook"), 
]