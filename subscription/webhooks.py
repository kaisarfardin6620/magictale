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
    subscription.stripe_subscription_id = stripe_sub.id
    subscription.status = stripe_sub.status
    
    if stripe_sub.items.data and hasattr(stripe_sub.items.data[0].price, 'lookup_key') and stripe_sub.items.data[0].price.lookup_key:
        subscription.plan = stripe_sub.items.data[0].price.lookup_key
    
    subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start) if stripe_sub.trial_start else None
    subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end) if stripe_sub.trial_end else None
    subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end) if stripe_sub.current_period_end else None
    subscription.canceled_at = timezone.datetime.fromtimestamp(stripe_sub.canceled_at) if stripe_sub.canceled_at else None
    subscription.save()
    _send_subscription_update(subscription)


def handle_checkout_session_completed(data_object):
    customer_id = data_object.get("customer")
    subscription_id = data_object.get("subscription")
    
    subscription = Subscription.objects.get(stripe_customer_id=customer_id)
    
    stripe_sub = stripe.Subscription.retrieve(subscription_id)
    _update_subscription_from_stripe_object(subscription, stripe_sub)

def handle_subscription_event(data_object):
    if data_object.get('object') == 'invoice':
        subscription_id = data_object.get('subscription')
    else: 
        subscription_id = data_object.get('id')
    
    if not subscription_id:
        print(f"Webhook event of type {data_object.get('object')} is missing a subscription ID.")
        return

    try:
        subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
    except Subscription.DoesNotExist:
        customer_id = data_object.get("customer")
        if not customer_id:
            print(f"CRITICAL: Webhook for unknown subscription {subscription_id} with no customer ID.")
            return
        try:
            subscription = Subscription.objects.get(stripe_customer_id=customer_id)
        except Subscription.DoesNotExist:
            print(f"CRITICAL: Webhook for unknown customer and subscription. Sub ID: {subscription_id}")
            return
    
    stripe_sub = stripe.Subscription.retrieve(subscription_id)
    _update_subscription_from_stripe_object(subscription, stripe_sub)


EVENT_HANDLER_MAP = {
    "checkout.session.completed": handle_checkout_session_completed,
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

    handler = EVENT_HANDLER_MAP.get(event["type"])

    if handler:
        try:
            handler(event["data"]["object"])
        except Exception as e:
            print(f"Error processing webhook {event.get('id', 'unknown')}: {e}")
    else:
        print(f"Unhandled event type: {event['type']}")

    return HttpResponse(status=200)