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
import logging

# It's better to use Django's logging framework
logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

def _send_subscription_update(subscription):
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
        logger.error(f"Error sending channel update: {e}")

def _update_subscription_from_stripe_object(subscription, stripe_sub):
    subscription.stripe_subscription_id = stripe_sub.id
    subscription.status = stripe_sub.status
    try:
        if stripe_sub.items.data:
            # Using price.product and then retrieving product might be more robust
            # if you have more complex subscription models in the future.
            # For now, this is fine.
            lookup_key = stripe_sub.items.data[0].price.lookup_key
            if lookup_key:
                subscription.plan = lookup_key
    except (AttributeError, IndexError, KeyError) as e:
        logger.warning(f"Could not update plan from lookup_key due to missing data: {e}")

    subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start) if stripe_sub.trial_start else None
    subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end) if stripe_sub.trial_end else None
    subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end) if stripe_sub.current_period_end else None
    subscription.canceled_at = timezone.datetime.fromtimestamp(stripe_sub.canceled_at) if stripe_sub.canceled_at else None
    subscription.save()
    logger.info(f"SUCCESS: Subscription {subscription.id} for user {subscription.user.id} updated to status '{subscription.status}'")
    _send_subscription_update(subscription)

def handle_checkout_session_completed(data_object):
    customer_id = data_object.get('customer')
    subscription_id = data_object.get('subscription')

    if not customer_id or not subscription_id:
        logger.error(f"Webhook event (checkout.session.completed) is missing a required ID. Customer: {customer_id}, Subscription: {subscription_id}")
        return

    try:
        # At this point, the subscription object should exist with "pending_confirmation"
        subscription_model = Subscription.objects.get(stripe_customer_id=customer_id)
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        _update_subscription_from_stripe_object(subscription_model, stripe_sub)
    except Subscription.DoesNotExist:
        logger.critical(f"CRITICAL: Webhook received for an unknown customer. Cus ID: {customer_id}")
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error while handling checkout session: {e}")


def handle_customer_subscription_event(data_object):
    subscription_id = data_object.get('id')
    if not subscription_id:
        logger.error("Webhook event (customer.subscription) is missing subscription ID.")
        return
        
    try:
        # Here we should have the stripe_subscription_id stored
        subscription_model = Subscription.objects.get(stripe_subscription_id=subscription_id)
        _update_subscription_from_stripe_object(subscription_model, data_object)
    except Subscription.DoesNotExist:
        # Fallback to customer ID if subscription ID is not yet stored
        customer_id = data_object.get('customer')
        if customer_id:
            try:
                subscription_model = Subscription.objects.get(stripe_customer_id=customer_id)
                _update_subscription_from_stripe_object(subscription_model, data_object)
            except Subscription.DoesNotExist:
                logger.critical(f"CRITICAL: Webhook for subscription {subscription_id} but no matching customer {customer_id} found.")
        else:
            logger.critical(f"CRITICAL: Webhook received for an unknown subscription. Sub ID: {subscription_id}")

# This can be simplified as many events just update the subscription status
def handle_invoice_paid(data_object):
    subscription_id = data_object.get('subscription')
    if not subscription_id:
        return # Not a subscription invoice

    try:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        subscription_model = Subscription.objects.get(stripe_subscription_id=stripe_sub.id)
        _update_subscription_from_stripe_object(subscription_model, stripe_sub)
    except Subscription.DoesNotExist:
        logger.warning(f"Invoice paid for a subscription not in our DB. Sub ID: {subscription_id}")
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error while handling invoice paid: {e}")


EVENT_HANDLER_MAP = {
    "checkout.session.completed": handle_checkout_session_completed,
    "customer.subscription.updated": handle_customer_subscription_event,
    "customer.subscription.deleted": handle_customer_subscription_event,
    "invoice.payment_succeeded": handle_invoice_paid,
    "invoice.paid": handle_invoice_paid,
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

    logger.info(f"Received Stripe event: {event['type']}")

    handler = EVENT_HANDLER_MAP.get(event["type"])
    if handler:
        try:
            handler(event["data"]["object"])
        except Exception as e:
            logger.fatal(f"FATAL ERROR processing webhook {event.get('id', 'unknown')}: {e}")
    else:
        logger.warning(f"Unhandled event type: {event['type']}")
    return HttpResponse(status=200)