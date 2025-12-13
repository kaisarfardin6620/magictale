import stripe
import datetime
import logging
import traceback
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import IntegrityError
from .models import Subscription, ProcessedStripeEvent
from .serializers import SubscriptionSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny

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
            logger.info(f"Sent channel update for user {subscription.user.id}")
    except Exception as e:
        logger.error(f"Error sending channel update for user {subscription.user.id}: {e}")

def _update_subscription_from_stripe_object(subscription_model, stripe_sub_object):
    logger.info(f"Starting database update for local subscription ID {subscription_model.id} from Stripe sub {stripe_sub_object.id}")
    subscription_model.stripe_subscription_id = stripe_sub_object.id
    subscription_model.status = stripe_sub_object.status
    try:
        price = stripe_sub_object['items']['data'][0]['price']
        if 'lookup_key' in price and price['lookup_key']:
            subscription_model.plan = price['lookup_key']
    except (AttributeError, IndexError, KeyError) as e:
        logger.warning(f"Could not get plan from lookup_key on subscription {stripe_sub_object.id}: {e}")

    trial_start_ts = getattr(stripe_sub_object, 'trial_start', None)
    trial_end_ts = getattr(stripe_sub_object, 'trial_end', None)
    current_period_end_ts = getattr(stripe_sub_object, 'current_period_end', None)
    canceled_at_ts = getattr(stripe_sub_object, 'canceled_at', None)

    subscription_model.trial_start = datetime.datetime.fromtimestamp(trial_start_ts, tz=timezone.utc) if trial_start_ts else None
    subscription_model.trial_end = datetime.datetime.fromtimestamp(trial_end_ts, tz=timezone.utc) if trial_end_ts else None
    subscription_model.current_period_end = datetime.datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc) if current_period_end_ts else None
    subscription_model.canceled_at = datetime.datetime.fromtimestamp(canceled_at_ts, tz=timezone.utc) if canceled_at_ts else None
    
    try:
        subscription_model.save()
        logger.info(f"SUCCESS: Subscription {subscription_model.id} for user {subscription_model.user.id} updated to status '{subscription_model.status}'")
    except Exception as e:
        logger.error(f"DATABASE SAVE FAILED for subscription {subscription_model.id}. Error: {e}")
        raise e

    _send_subscription_update(subscription_model)


def handle_checkout_session_completed(session_object):
    customer_id = session_object.get('customer')
    subscription_id = session_object.get('subscription')
    
    if not customer_id or not subscription_id:
        logger.error("Checkout session completed event is missing customer_id or subscription_id.")
        return

    try:
        subscription_model = Subscription.objects.get(stripe_customer_id=customer_id)
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        _update_subscription_from_stripe_object(subscription_model, stripe_sub)
    except Subscription.DoesNotExist:
        logger.critical(f"FATAL: Received checkout.session.completed for customer {customer_id} but no matching subscription was found.")
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error while handling checkout session {session_object.id}: {e}")

def handle_customer_subscription_event(subscription_object):
    subscription_id = subscription_object.get('id')
    if not subscription_id:
        logger.error("customer.subscription event is missing subscription ID.")
        return

    try:
        subscription_model = Subscription.objects.get(stripe_subscription_id=subscription_id)
        _update_subscription_from_stripe_object(subscription_model, subscription_object)
    except Subscription.DoesNotExist:
        logger.warning(f"Received subscription update for {subscription_id} but no matching subscription was found.")
    except Exception as e:
        logger.critical(f"Unexpected error in handle_customer_subscription_event for {subscription_id}: {e}")

EVENT_HANDLER_MAP = {
    "checkout.session.completed": handle_checkout_session_completed,
    "customer.subscription.updated": handle_customer_subscription_event,
    "customer.subscription.deleted": handle_customer_subscription_event,
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
        logger.error(f"Webhook signature verification failed. Error: {e}")
        return HttpResponseBadRequest(f"Webhook error: {e}")

    event_id = event.get('id')
    
    try:
        if event_id:
            ProcessedStripeEvent.objects.create(event_id=event_id)
    except IntegrityError:
        logger.info(f"Webhook event {event_id} has already been processed. Ignoring.")
        return HttpResponse(status=200)

    logger.info(f"Received valid Stripe event: '{event['type']}' (ID: {event.get('id')})")
    handler = EVENT_HANDLER_MAP.get(event["type"])
    if handler:
        try:
            handler(event["data"]["object"])
        except Exception as e:
            logger.critical(f"FATAL ERROR processing webhook {event.get('id', 'unknown')}: {e}\n{traceback.format_exc()}")
    else:
        logger.warning(f"Unhandled event type: '{event['type']}'")
    return HttpResponse(status=200)