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
        
        # --- UPDATED LOGIC ---
        # Try to get an existing Stripe customer ID from the user's subscription
        try:
            subscription = user.subscription
            customer_id = subscription.stripe_customer_id
        except Subscription.DoesNotExist:
            # If no subscription record exists, create a new Stripe customer
            customer = stripe.Customer.create(email=user.email)
            customer_id = customer.id
        # --- END OF UPDATED LOGIC ---

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer=customer_id, # Use the existing or new customer_id
            line_items=[{
                "price": PRICE_IDS[plan],
                "quantity": 1,
            }],
            mode="subscription",
            subscription_data={"trial_period_days": 14},
            success_url="http://localhost:3000/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="http://localhost:3000/cancel",
        )

        # Create or update the local subscription record with the customer ID
        # Subscription.objects.update_or_create(
        #     user=user,
        #     defaults={
        #         "stripe_customer_id": customer_id,
        #         "plan": plan,
        #         # The webhook will update the status to 'trialing' or 'active' later
        #     }
        # )

        return Response({"checkout_url": checkout_session.url})


        Subscription.objects.update_or_create(
    user=user,
    defaults={
        "stripe_customer_id": customer_id,
        "plan": plan,
        # Let's set a temporary status. The webhook will finalize it.
        "status": "pending_confirmation", 
    }
)