import stripe
from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Subscription
from .serializers import SubscriptionSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY

PRICE_IDS = {
    "creator": "price_1RwsTM090fCkwKBzzGwDxzmH",  
    "master": "price_1RwsTi090fCkwKBzS2iIzA9n",  
}

class SubscriptionViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["post"])
    def create_checkout(self, request):
        plan = request.data.get("plan")
        if plan not in PRICE_IDS:
            return Response({"error": "Invalid plan"}, status=400)

        user = request.user
        customer = stripe.Customer.create(
            email=user.email
        )

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer=customer.id,
            line_items=[{
                "price": PRICE_IDS[plan],
                "quantity": 1,
            }],
            mode="subscription",
            subscription_data={
                "trial_period_days": 14
            },
            success_url="http://localhost:3000/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="http://localhost:3000/cancel",
        )

        Subscription.objects.update_or_create(
            user=user,
            defaults={
                "stripe_customer_id": customer.id,
                "plan": plan,
                "status": "trialing",
            }
        )

        return Response({"checkout_url": checkout_session.url})

    @action(detail=False, methods=["get"])
    def my_subscription(self, request):
        sub = getattr(request.user, "subscription", None)
        if not sub:
            return Response({"detail": "No subscription"}, status=404)
        return Response(SubscriptionSerializer(sub).data)