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
import traceback

# Use Django's logging framework
logger = logging.getLogger(__name__)

# Set your Stripe API key from settings
stripe.api_key = settings.STRIPE_SECRET_KEY

def _send_subscription_update(subscription):
    """
    Sends a real-time update to the frontend via Django Channels if configured.
    """
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
    """
    Updates the local Subscription model instance using a fresh Stripe Subscription object.
    This is the core logic that syncs your DB with Stripe's data.
    """
    logger.info(f"Starting database update for local subscription ID {subscription_model.id} from Stripe sub {stripe_sub_object.id}")
    
    # Always update the stripe_subscription_id, as it might be the first time we're seeing it
    subscription_model.stripe_subscription_id = stripe_sub_object.id
    subscription_model.status = stripe_sub_object.status
    
    # Safely update the plan based on the price's lookup_key
    try:
        if stripe_sub_object.items and stripe_sub_object.items.data:
            price = stripe_sub_object.items.data[0].price
            if price and price.lookup_key:
                logger.info(f"Found lookup_key '{price.lookup_key}' in Stripe. Setting as local plan.")
                subscription_model.plan = price.lookup_key
            else:
                logger.warning(f"Price object for {stripe_sub_object.id} did not have a lookup_key. Plan will not be updated.")
    except (AttributeError, IndexError, KeyError) as e:
        logger.warning(f"Could not get plan from lookup_key on subscription {stripe_sub_object.id}: {e}")

    # Convert Unix timestamps from Stripe into timezone-aware datetime objects
    subscription_model.trial_start = timezone.datetime.fromtimestamp(stripe_sub_object.trial_start, tz=timezone.utc) if stripe_sub_object.trial_start else None
    subscription_model.trial_end = timezone.datetime.fromtimestamp(stripe_sub_object.trial_end, tz=timezone.utc) if stripe_sub_object.trial_end else None
    subscription_model.current_period_end = timezone.datetime.fromtimestamp(stripe_sub_object.current_period_end, tz=timezone.utc) if stripe_sub_object.current_period_end else None
    subscription_model.canceled_at = timezone.datetime.fromtimestamp(stripe_sub_object.canceled_at, tz=timezone.utc) if stripe_sub_object.canceled_at else None
    
    try:
        # Save the updated model to the database
        subscription_model.save()
        logger.info(f"SUCCESS: Subscription {subscription_model.id} for user {subscription_model.user.id} updated to status '{subscription_model.status}'")
    except Exception as e:
        logger.error(f"DATABASE SAVE FAILED for subscription {subscription_model.id}. Error: {e}")
        # Re-raise the exception to be caught by the main handler for full traceback logging
        raise e

    # Send a real-time update to the user's frontend
    _send_subscription_update(subscription_model)

def handle_subscription_event(data_object):
    """
    A unified handler for all webhook events related to a subscription.
    """
    event_type = data_object.get('object', 'unknown')
    logger.info(f"Handling subscription event for object type: '{event_type}'")

    subscription_id = None
    customer_id = data_object.get('customer')

    # --- THIS IS THE CORRECTED LOGIC FOR EXTRACTING THE ID ---
    if event_type == 'subscription':
        # For events like 'customer.subscription.updated', the ID is in the 'id' field of the object
        subscription_id = data_object.get('id')
    else:
        # For events like 'checkout.session.completed' or 'invoice.paid', it's in the 'subscription' field
        subscription_id = data_object.get('subscription')
    # -----------------------------------------------------------

    if not subscription_id:
        logger.warning(f"Webhook event of type '{event_type}' has no subscription ID. This may be normal (e.g., a one-time payment invoice). Ignoring.")
        return

    logger.info(f"Extracted Stripe Subscription ID: {subscription_id}")
    logger.info(f"Extracted Stripe Customer ID: {customer_id}")

    try:
        logger.info(f"Fetching full subscription object for '{subscription_id}' from Stripe API...")
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        logger.info(f"Successfully fetched Stripe subscription object. Status: '{stripe_sub.status}'")
        
        subscription_model = None
        # Robustly find the local subscription record to update
        try:
            # First, try the most reliable lookup: the unique subscription ID
            subscription_model = Subscription.objects.get(stripe_subscription_id=stripe_sub.id)
            logger.info(f"Found local subscription model using stripe_subscription_id: {stripe_sub.id}")
        except Subscription.DoesNotExist:
            logger.warning(f"Could not find local subscription with stripe_subscription_id={stripe_sub.id}. Falling back to customer_id.")
            if customer_id:
                try:
                    # Fallback for the first event (checkout.session.completed) where we only have the customer ID
                    subscription_model = Subscription.objects.get(stripe_customer_id=customer_id)
                    logger.info(f"Found local subscription model using stripe_customer_id: {customer_id}")
                except Subscription.DoesNotExist:
                    logger.critical(f"FATAL: No local subscription found for EITHER stripe_subscription_id OR stripe_customer_id ({customer_id}). Cannot update.")
                    return
            else:
                logger.critical("FATAL: Cannot find local subscription and no customer_id was provided in the event to fall back on.")
                return

        # If we found a model one way or another, update it with the fresh data from Stripe's API
        if subscription_model:
            _update_subscription_from_stripe_object(subscription_model, stripe_sub)

    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error while processing subscription {subscription_id}: {e}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in handle_subscription_event for subscription {subscription_id}: {e}")
        # Re-raise to be caught by the main webhook handler, which will log the full traceback
        raise

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
    """
    The main entry point for all incoming Stripe webhooks.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret=endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"Webhook signature verification failed. Error: {e}")
        return HttpResponseBadRequest(f"Webhook error: {e}")
    
    logger.info(f"Received valid Stripe event: '{event['type']}' (ID: {event.get('id')})")
    
    handler = EVENT_HANDLER_MAP.get(event["type"])
    if handler:
        try:
            # Pass the event data object to the appropriate handler
            handler(event["data"]["object"])
        except Exception as e:
            # Log the full traceback for any unhandled exception in the handler
            logger.critical(f"FATAL ERROR processing webhook {event.get('id', 'unknown')}: {e}\n{traceback.format_exc()}")
    else:
        logger.warning(f"Unhandled event type: '{event['type']}'")
        
    # Always return a 200 OK to Stripe to acknowledge receipt of the event
    return HttpResponse(status=200)