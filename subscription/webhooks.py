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

def _update_subscription_from_stripe_object(subscription_model, stripe_sub_object):
    subscription_model.stripe_subscription_id = stripe_sub_object.id
    subscription_model.status = stripe_sub_object.status
    
    try:
        if stripe_sub_object.items and stripe_sub_object.items.data:
            price = stripe_sub_object.items.data[0].price
            if price and price.lookup_key:
                subscription_model.plan = price.lookup_key
    except (AttributeError, IndexError, KeyError) as e:
        logger.warning(f"Could not update plan from lookup_key on subscription {stripe_sub_object.id}: {e}")

    subscription_model.trial_start = timezone.datetime.fromtimestamp(stripe_sub_object.trial_start) if stripe_sub_object.trial_start else None
    subscription_model.trial_end = timezone.datetime.fromtimestamp(stripe_sub_object.trial_end) if stripe_sub_object.trial_end else None
    subscription_model.current_period_end = timezone.datetime.fromtimestamp(stripe_sub_object.current_period_end) if stripe_sub_object.current_period_end else None
    subscription_model.canceled_at = timezone.datetime.fromtimestamp(stripe_sub_object.canceled_at) if stripe_sub_object.canceled_at else None
    subscription_model.save()
    logger.info(f"SUCCESS: Subscription {subscription_model.id} for user {subscription_model.user.id} updated to status '{subscription_model.status}'")
    _send_subscription_update(subscription_model)

def handle_subscription_event(data_object):
    subscription_id = None
    customer_id = data_object.get('customer')

    if data_object.get('object') == 'subscription':
        subscription_id = data_object.get('id')
        subscription_id = data_object.get('subscription')

    if not subscription_id:
        logger.info(f"Webhook event of type '{data_object.get('object')}' received without a subscription ID. Ignoring.")
        return

    try:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        
        try:
            subscription_model = Subscription.objects.get(stripe_subscription_id=stripe_sub.id)
        except Subscription.DoesNotExist:
            if customer_id:
                subscription_model = Subscription.objects.get(stripe_customer_id=customer_id)
            else:
                customer_id_from_sub = stripe_sub.customer
                logger.critical(f"CRITICAL: Webhook for sub {stripe_sub.id} received, but no matching local subscription found by subscription OR customer ID ({customer_id_from_sub}).")
                return

        _update_subscription_from_stripe_object(subscription_model, stripe_sub)
    except Subscription.DoesNotExist:
        logger.critical(f"CRITICAL: Webhook received, but no subscription model found for customer {customer_id} or subscription {subscription_id}")
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error while handling webhook: {e}")


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
    
    logger.info(f"Received Stripe event: {event['type']}")
    
    handler = EVENT_HANDLER_MAP.get(event["type"])
    if handler:
        try:
            handler(event["data"]["object"])
        except Exception as e:
            import traceback
            logger.critical(f"FATAL ERROR processing webhook {event.get('id', 'unknown')}: {e}\n{traceback.format_exc()}")
    else:
        logger.warning(f"Unhandled event type: {event['type']}")
    return HttpResponse(status=200)