import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Subscription
from .serializers import SubscriptionSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

stripe.api_key = settings.STRIPE_SECRET_KEY

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event["type"] in ["customer.subscription.created", "customer.subscription.updated"]:
        sub_data = event["data"]["object"]
        
        stripe_sub_id = sub_data.get("id")
        status = sub_data.get("status")
        stripe_customer_id = sub_data.get("customer")
        
        current_period_end_timestamp = sub_data.get("current_period_end")
        if current_period_end_timestamp:
            current_period_end = timezone.datetime.fromtimestamp(current_period_end_timestamp)
        else:
            current_period_end = None

        try:
            sub = Subscription.objects.get(
                stripe_customer_id=stripe_customer_id
            )
            
            sub.stripe_subscription_id = stripe_sub_id
            sub.status = status
            sub.current_period_end = current_period_end
            sub.save()
            
            channel_layer = get_channel_layer()
            if channel_layer:
                serializer = SubscriptionSerializer(sub)
                status_data = serializer.data
                user_group_name = f"user_{sub.user.id}"
                async_to_sync(channel_layer.group_send)(
                    user_group_name,
                    {
                        "type": "send_subscription_update",
                        "status_data": status_data
                    }
                )

        except Subscription.DoesNotExist:
            pass

    return HttpResponse(status=200)
