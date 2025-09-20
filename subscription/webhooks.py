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

def handle_checkout_session_completed(data_object):
    customer_id = data_object.get("customer")
    subscription_id = data_object.get("subscription")

    if not customer_id or not subscription_id:
        raise ValueError("Missing customer ID or subscription ID.")

    subscription = Subscription.objects.get(stripe_customer_id=customer_id)

    if subscription.stripe_subscription_id == subscription_id:
        print(f"Webhook event for {subscription_id} already processed.")
        return

    stripe_sub = stripe.Subscription.retrieve(subscription_id)
    subscription.stripe_subscription_id = stripe_sub.id
    subscription.status = stripe_sub.status
    subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start) if getattr(stripe_sub, 'trial_start', None) else None
    subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end) if getattr(stripe_sub, 'trial_end', None) else None
    subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end) if getattr(stripe_sub, 'current_period_end', None) else None
    subscription.canceled_at = None
    subscription.save()
    _send_subscription_update(subscription)

def handle_subscription_updated(data_object):
    subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
    
    subscription.status = data_object.get("status")
    subscription.current_period_end = timezone.datetime.fromtimestamp(data_object.get("current_period_end")) if data_object.get("current_period_end") else None
    subscription.canceled_at = None 
    subscription.save()
    _send_subscription_update(subscription)

def handle_subscription_deleted(data_object):
    subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))

    if subscription.status == "canceled":
        print(f"Webhook event for deleted subscription {subscription.stripe_subscription_id} already processed.")
        return

    subscription.status = "canceled"
    subscription.current_period_end = None
    subscription.canceled_at = timezone.datetime.fromtimestamp(data_object.get("canceled_at")) if data_object.get("canceled_at") else timezone.now()
    subscription.save()
    _send_subscription_update(subscription)

EVENT_HANDLER_MAP = {
    "checkout.session.completed": handle_checkout_session_completed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
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
        except Subscription.DoesNotExist:
            print(f"CRITICAL: Webhook received for an unknown subscription. Event: {event['type']}")
            return HttpResponse(status=200)
        except Exception as e:
            print(f"Error processing webhook {event.get('id', 'unknown')}: {e}")
            return HttpResponse(status=500)
    else:
        print(f"Unhandled event type: {event['type']}")

    return HttpResponse(status=200)


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