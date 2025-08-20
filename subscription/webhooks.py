# subscription/webhooks.py

import stripe
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Subscription
from .serializers import SubscriptionSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# === THESE IMPORTS ARE THE FIX ===
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
# =================================

stripe.api_key = settings.STRIPE_SECRET_KEY

def _send_subscription_update(subscription):
    """Send subscription updates via WebSocket to the user's group."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            serializer = SubscriptionSerializer(subscription)
            status_data = serializer.data
            user_group_name = f"user_{subscription.user.id}"
            async_to_sync(channel_layer.group_send)(
                user_group_name,
                {"type": "send_subscription_update", "status_data": status_data}
            )
    except Exception as e:
        print(f"Error sending channel update: {e}")

# --- THESE DECORATORS ARE THE FIX ---
@csrf_exempt
@api_view(['POST'])
@authentication_classes([]) # Tell DRF to NOT run ANY authentication for this view
@permission_classes([AllowAny]) # Tell DRF that anonymous users are allowed
def stripe_webhook(request):
    """Handle incoming Stripe webhook events securely and idempotently."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=endpoint_secret
        )
    except ValueError as e:
        return HttpResponseBadRequest(f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        return HttpResponseBadRequest(f"Invalid signature: {e}")

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")

            if not customer_id or not subscription_id:
                return HttpResponse(status=400, content="Missing customer ID or subscription ID.")

            subscription = Subscription.objects.get(stripe_customer_id=customer_id)

            if subscription.stripe_subscription_id == subscription_id:
                print(f"Webhook event checkout.session.completed for {subscription_id} already processed.")
                return HttpResponse(status=200)

            stripe_sub = stripe.Subscription.retrieve(subscription_id)

            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status
            subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start) if getattr(stripe_sub, 'trial_start', None) else None
            subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end) if getattr(stripe_sub, 'trial_end', None) else None
            subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end) if getattr(stripe_sub, 'current_period_end', None) else None
            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.updated":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))

            new_status = data_object.get("status")
            new_period_end = timezone.datetime.fromtimestamp(data_object.get("current_period_end")) if data_object.get("current_period_end") else None

            if subscription.status == new_status and subscription.current_period_end == new_period_end:
                print(f"Webhook event customer.subscription.updated for {subscription.stripe_subscription_id} contains no new data.")
                return HttpResponse(status=200)

            subscription.status = new_status
            subscription.current_period_end = new_period_end
            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.deleted":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))

            if subscription.status == "canceled":
                print(f"Webhook event customer.subscription.deleted for {subscription.stripe_subscription_id} already processed.")
                return HttpResponse(status=200)

            subscription.status = "canceled"
            subscription.current_period_end = None
            subscription.canceled_at = timezone.datetime.fromtimestamp(data_object.get("canceled_at")) if data_object.get("canceled_at") else timezone.now()
            subscription.save()
            _send_subscription_update(subscription)

        else:
            print(f"Unhandled event type: {event_type}")
            return HttpResponse(status=200)

    except Subscription.DoesNotExist:
        print(f"CRITICAL: Webhook received for an unknown subscription. Customer ID: {data_object.get('customer')}, Subscription ID: {data_object.get('id')}")
        return HttpResponse(status=200)
    except Exception as e:
        print(f"Error processing webhook {event.get('id', 'unknown')}: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)