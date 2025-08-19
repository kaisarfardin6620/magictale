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
        print(f"Error sending channel update: {e}")

@csrf_exempt
def stripe_webhook(request):
    """Handle incoming Stripe webhook events securely."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponseBadRequest(f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponseBadRequest(f"Invalid signature: {e}")

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            # The most reliable way to handle this is to use the `customer_details`
            # which provides the customer's email or other info to find the user.
            customer_email = data_object.get("customer_details", {}).get("email")
            subscription_id = data_object.get("subscription")

            if not customer_email or not subscription_id:
                return HttpResponse(status=400, content="Missing customer email or subscription ID.")

            # Retrieve the full subscription object from Stripe
            stripe_sub = stripe.Subscription.retrieve(subscription_id)

            # Find the local subscription record using the user's email
            # This assumes your user model has an email field.
            subscription = Subscription.objects.get(user__email=customer_email)

            # Update the local record
            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status

            if stripe_sub.trial_end:
                subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)
                subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)

            if stripe_sub.trial_start:
                subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.updated":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = data_object.get("status")

            period_end_ts = data_object.get("trial_end") or data_object.get("current_period_end")
            if period_end_ts:
                subscription.current_period_end = timezone.datetime.fromtimestamp(period_end_ts)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.deleted":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = "canceled"
            subscription.current_period_end = None
            subscription.canceled_at = timezone.now()
            subscription.save()
            _send_subscription_update(subscription)

        else:
            print(f"Unhandled event type: {event_type}")

    except Subscription.DoesNotExist:
        print("Webhook received for unknown customer/subscription.")
        pass
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)
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
        print(f"Error sending channel update: {e}")

@csrf_exempt
def stripe_webhook(request):
    """Handle incoming Stripe webhook events securely."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponseBadRequest(f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponseBadRequest(f"Invalid signature: {e}")

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            # The most reliable way to handle this is to use the `customer_details`
            # which provides the customer's email or other info to find the user.
            customer_email = data_object.get("customer_details", {}).get("email")
            subscription_id = data_object.get("subscription")

            if not customer_email or not subscription_id:
                return HttpResponse(status=400, content="Missing customer email or subscription ID.")

            # Retrieve the full subscription object from Stripe
            stripe_sub = stripe.Subscription.retrieve(subscription_id)

            # Find the local subscription record using the user's email
            # This assumes your user model has an email field.
            subscription = Subscription.objects.get(user__email=customer_email)

            # Update the local record
            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status

            if stripe_sub.trial_end:
                subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)
                subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)

            if stripe_sub.trial_start:
                subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.updated":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = data_object.get("status")

            period_end_ts = data_object.get("trial_end") or data_object.get("current_period_end")
            if period_end_ts:
                subscription.current_period_end = timezone.datetime.fromtimestamp(period_end_ts)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.deleted":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = "canceled"
            subscription.current_period_end = None
            subscription.canceled_at = timezone.now()
            subscription.save()
            _send_subscription_update(subscription)

        else:
            print(f"Unhandled event type: {event_type}")

    except Subscription.DoesNotExist:
        print("Webhook received for unknown customer/subscription.")
        pass
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)
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
        print(f"Error sending channel update: {e}")

@csrf_exempt
def stripe_webhook(request):
    """Handle incoming Stripe webhook events securely."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponseBadRequest(f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponseBadRequest(f"Invalid signature: {e}")

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            # The most reliable way to handle this is to use the `customer_details`
            # which provides the customer's email or other info to find the user.
            customer_email = data_object.get("customer_details", {}).get("email")
            subscription_id = data_object.get("subscription")

            if not customer_email or not subscription_id:
                return HttpResponse(status=400, content="Missing customer email or subscription ID.")

            # Retrieve the full subscription object from Stripe
            stripe_sub = stripe.Subscription.retrieve(subscription_id)

            # Find the local subscription record using the user's email
            # This assumes your user model has an email field.
            subscription = Subscription.objects.get(user__email=customer_email)

            # Update the local record
            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status

            if stripe_sub.trial_end:
                subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)
                subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)

            if stripe_sub.trial_start:
                subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.updated":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = data_object.get("status")

            period_end_ts = data_object.get("trial_end") or data_object.get("current_period_end")
            if period_end_ts:
                subscription.current_period_end = timezone.datetime.fromtimestamp(period_end_ts)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.deleted":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = "canceled"
            subscription.current_period_end = None
            subscription.canceled_at = timezone.now()
            subscription.save()
            _send_subscription_update(subscription)

        else:
            print(f"Unhandled event type: {event_type}")

    except Subscription.DoesNotExist:
        print("Webhook received for unknown customer/subscription.")
        pass
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)
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
        print(f"Error sending channel update: {e}")

@csrf_exempt
def stripe_webhook(request):
    """Handle incoming Stripe webhook events securely."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponseBadRequest(f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponseBadRequest(f"Invalid signature: {e}")

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            # The most reliable way to handle this is to use the `customer_details`
            # which provides the customer's email or other info to find the user.
            customer_email = data_object.get("customer_details", {}).get("email")
            subscription_id = data_object.get("subscription")

            if not customer_email or not subscription_id:
                return HttpResponse(status=400, content="Missing customer email or subscription ID.")

            # Retrieve the full subscription object from Stripe
            stripe_sub = stripe.Subscription.retrieve(subscription_id)

            # Find the local subscription record using the user's email
            # This assumes your user model has an email field.
            subscription = Subscription.objects.get(user__email=customer_email)

            # Update the local record
            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status

            if stripe_sub.trial_end:
                subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)
                subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)

            if stripe_sub.trial_start:
                subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.updated":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = data_object.get("status")

            period_end_ts = data_object.get("trial_end") or data_object.get("current_period_end")
            if period_end_ts:
                subscription.current_period_end = timezone.datetime.fromtimestamp(period_end_ts)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.deleted":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = "canceled"
            subscription.current_period_end = None
            subscription.canceled_at = timezone.now()
            subscription.save()
            _send_subscription_update(subscription)

        else:
            print(f"Unhandled event type: {event_type}")

    except Subscription.DoesNotExist:
        print("Webhook received for unknown customer/subscription.")
        pass
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)
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
        print(f"Error sending channel update: {e}")

@csrf_exempt
def stripe_webhook(request):
    """Handle incoming Stripe webhook events securely."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponseBadRequest(f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponseBadRequest(f"Invalid signature: {e}")

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            # The most reliable way to handle this is to use the `customer_details`
            # which provides the customer's email or other info to find the user.
            customer_email = data_object.get("customer_details", {}).get("email")
            subscription_id = data_object.get("subscription")

            if not customer_email or not subscription_id:
                return HttpResponse(status=400, content="Missing customer email or subscription ID.")

            # Retrieve the full subscription object from Stripe
            stripe_sub = stripe.Subscription.retrieve(subscription_id)

            # Find the local subscription record using the user's email
            # This assumes your user model has an email field.
            subscription = Subscription.objects.get(user__email=customer_email)

            # Update the local record
            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status

            if stripe_sub.trial_end:
                subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)
                subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)

            if stripe_sub.trial_start:
                subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.updated":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = data_object.get("status")

            period_end_ts = data_object.get("trial_end") or data_object.get("current_period_end")
            if period_end_ts:
                subscription.current_period_end = timezone.datetime.fromtimestamp(period_end_ts)

            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.deleted":
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = "canceled"
            subscription.current_period_end = None
            subscription.canceled_at = timezone.now()
            subscription.save()
            _send_subscription_update(subscription)

        else:
            print(f"Unhandled event type: {event_type}")

    except Subscription.DoesNotExist:
        print("Webhook received for unknown customer/subscription.")
        pass
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)
