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
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny

stripe.api_key = settings.STRIPE_SECRET_KEY

def _send_subscription_update(subscription):
    """ Helper to send a real-time update via WebSocket. """
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            serializer = SubscriptionSerializer(subscription)
            user_group_name = f"user_{subscription.user.id}"
            async_to_sync(channel_layer.group_send)(
                user_group_name,
                {"type": "send_subscription_update", "status_data": serializer.data}
            )
    except Exception as e:
        print(f"Error sending channel update: {e}")

def _update_subscription_from_stripe_object(subscription, stripe_sub):
    """
    Central helper to update the local DB from a Stripe subscription object.
    This version is resilient to missing data from the Stripe API.
    """
    subscription.stripe_subscription_id = stripe_sub.id
    subscription.status = stripe_sub.status
    
    # --- THIS IS THE BULLETPROOF FIX ---
    # It safely checks every level of the object to prevent any crashes
    # if the 'lookup_key' is missing from the Stripe event data.
    try:
        if stripe_sub.items.data:
            lookup_key = stripe_sub.items.data[0].price.lookup_key
            if lookup_key:
                subscription.plan = lookup_key
    except (AttributeError, IndexError, KeyError) as e:
        print(f"Could not update plan from lookup_key due to missing data: {e}")
    # ---------------------------------

    subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start) if stripe_sub.trial_start else None
    subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end) if stripe_sub.trial_end else None
    subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end) if stripe_sub.current_period_end else None
    subscription.canceled_at = timezone.datetime.fromtimestamp(stripe_sub.canceled_at) if stripe_sub.canceled_at else None
    
    subscription.save()
    print(f"SUCCESS: Subscription {subscription.id} for user {subscription.user.id} updated to status '{subscription.status}'")
    _send_subscription_update(subscription)

def handle_subscription_event(data_object):
    """ A single, robust handler for ALL subscription-related webhook events. """
    subscription_id = None
    customer_id = None

    if data_object.get('object') == 'checkout.session':
        subscription_id = data_object.get('subscription')
        customer_id = data_object.get('customer')
    else: # Handles invoice and subscription objects
        subscription_id = data_object.get('subscription', data_object.get('id'))
        customer_id = data_object.get('customer')

    if not subscription_id or not customer_id:
        print(f"Webhook event (type: {data_object.get('object')}) is missing a required ID.")
        return

    try:
        # We now ALWAYS find the subscription by customer ID first. This is guaranteed
        # to exist in our database after the checkout session is created.
        subscription = Subscription.objects.get(stripe_customer_id=customer_id)
    except Subscription.DoesNotExist:
        print(f"CRITICAL: Webhook received for an unknown customer. Cus ID: {customer_id}")
        return
    
    # ALWAYS fetch the latest subscription state directly from Stripe's API.
    stripe_sub = stripe.Subscription.retrieve(subscription_id)
    _update_subscription_from_stripe_object(subscription, stripe_sub)

EVENT_HANDLER_MAP = {
    "checkout.session.completed": handle_subscription_event,
    "customer.subscription.updated": handle_subscription_event,
    "customer.subscription.deleted": handle_subscription_event,
    "invoice.payment_succeeded": handle_subscription_event,
    "invoice.paid": handle_subscription_event,
}

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret=endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return HttpResponseBadRequest(f"Webhook error: {e}")
    
    print(f"Received Stripe event: {event['type']}")
    
    handler = EVENT_HANDLER_MAP.get(event["type"])
    if handler:
        try:
            handler(event["data"]["object"])
        except Exception as e:
            print(f"FATAL ERROR processing webhook {event.get('id', 'unknown')}: {e}")
    else:
        print(f"Unhandled event type: {event['type']}")
    return HttpResponse(status=200)