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
        # It's good practice to log this error in a real production environment
        print(f"Error sending channel update: {e}")

@csrf_exempt
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
            customer_email = data_object.get("customer_details", {}).get("email")
            subscription_id = data_object.get("subscription")

            if not customer_email or not subscription_id:
                return HttpResponse(status=400, content="Missing customer email or subscription ID.")

            # Find the local subscription record
            subscription = Subscription.objects.get(user__email=customer_email)

            # --- IDEMPOTENCY CHECK ---
            # If we already have the Stripe subscription ID, this checkout has likely been processed.
            if subscription.stripe_subscription_id == subscription_id:
                print(f"Webhook event checkout.session.completed for {subscription_id} already processed.")
                return HttpResponse(status=200) # Acknowledge the event, but do nothing.

            # Retrieve the full subscription object from Stripe
            stripe_sub = stripe.Subscription.retrieve(subscription_id)

            # Update the local record
            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status
            subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start) if stripe_sub.trial_start else None
            subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end) if stripe_sub.trial_end else None
            subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end) if stripe_sub.current_period_end else None
            subscription.canceled_at = None # Ensure this is cleared on new subscription
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
            subscription.current_period_end = None # Canceled subs don't have an active period end
            subscription.canceled_at = timezone.datetime.fromtimestamp(data_object.get("canceled_at")) if data_object.get("canceled_at") else timezone.now()
            subscription.save()
            _send_subscription_update(subscription)

        else:
            print(f"Unhandled event type: {event_type}")

    except Subscription.DoesNotExist:
        print(f"Webhook received for an unknown subscription: {data_object.get('id')}")
        pass
    except Exception as e:
        print(f"Error processing webhook {event['id']}: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)