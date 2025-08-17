
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SubscriptionViewSet
from .webhooks import stripe_webhook  # Added this import

router = DefaultRouter()
router.register(r"subscriptions", SubscriptionViewSet, basename="subscriptions")

urlpatterns = [
    path("", include(router.urls)),
    path("webhook/", stripe_webhook, name="stripe-webhook"),
]
