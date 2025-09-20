import stripe
from django.conf import settings
import os
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Subscription
from .serializers import SubscriptionSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY

PRICE_IDS = {
    "creator": os.getenv("STRIPE_CREATOR_PRICE_ID"),
    "master": os.getenv("STRIPE_MASTER_PRICE_ID"),
}

class SubscriptionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"], url_path='create-checkout')
    def create_checkout(self, request):
        plan = request.data.get("plan")
        if plan not in PRICE_IDS or not PRICE_IDS[plan]:
            return Response(
                {"detail": "Invalid plan specified or Price ID not configured."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        customer_id = None
        try:
            subscription = user.subscription
            customer_id = subscription.stripe_customer_id
        except Subscription.DoesNotExist:
            customer = stripe.Customer.create(email=user.email, name=user.get_full_name(), metadata={'user_id': user.id})
            customer_id = customer.id

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                customer=customer_id,
                line_items=[{
                    "price": PRICE_IDS[plan],
                    "quantity": 1,
                }],
                mode="subscription",
                subscription_data={"trial_period_days": 14},
                success_url=settings.FRONTEND_URL + "/payment-success?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=settings.FRONTEND_URL + "/payment-cancelled",
            )

            Subscription.objects.update_or_create(
                user=user,
                defaults={
                    "stripe_customer_id": customer_id,
                    "plan": plan,
                    "status": "pending_confirmation",
                }
            )
            return Response(
                {"checkout_url": checkout_session.url},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["post"], url_path='manage-portal')
    def create_portal_session(self, request):
        user = request.user
        try:
            subscription = user.subscription
            customer_id = subscription.stripe_customer_id
        except Subscription.DoesNotExist:
            return Response(
                {"detail": "User does not have a subscription to manage."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return_url = settings.FRONTEND_URL + '/profile/subscription'

        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return Response(
                {"portal_url": portal_session.url},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)