# import stripe
# from django.conf import settings
# from django.http import HttpResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.utils import timezone
# from .models import Subscription
# from .serializers import SubscriptionSerializer
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync

# # Set the Stripe API key from settings
# stripe.api_key = settings.STRIPE_SECRET_KEY

# def _send_subscription_update(subscription):
#     """
#     Helper function to send a real-time update to the user via Django Channels.
#     """
#     try:
#         channel_layer = get_channel_layer()
#         if channel_layer:
#             # Serialize the subscription data to send to the frontend
#             serializer = SubscriptionSerializer(subscription)
#             status_data = serializer.data
            
#             # The group name is unique to the user
#             user_group_name = f"user_{subscription.user.id}"
            
#             # Send the message to the user's group
#             async_to_sync(channel_layer.group_send)(
#                 user_group_name,
#                 {
#                     "type": "send_subscription_update", # This corresponds to a method in your consumer
#                     "status_data": status_data
#                 }
#             )
#     except Exception as e:
#         # It's good practice to log errors, especially in background tasks
#         print(f"Error sending channel update: {e}")


# @csrf_exempt
# def stripe_webhook(request):
#     """
#     Handles incoming webhooks from Stripe to update subscription statuses.
#     """
#     payload = request.body
#     sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    
#     # Verify the event is from Stripe
#     try:
#         event = stripe.Webhook.construct_event(
#             payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
#         )
#     except ValueError as e:
#         # Invalid payload
#         return HttpResponse(status=400)
#     except stripe.error.SignatureVerificationError as e:
#         # Invalid signature
#         return HttpResponse(status=400)

#     # Get the event data
#     event_type = event["type"]
#     sub_data = event["data"]["object"]
#     stripe_customer_id = sub_data.get("customer")

#     if not stripe_customer_id:
#         # If there's no customer ID, we can't process it
#         return HttpResponse(status=400, content="Webhook Error: Missing customer ID.")

#     try:
#         # Find the local subscription record using the customer ID
#         subscription = Subscription.objects.get(stripe_customer_id=stripe_customer_id)
        
#         # Handle the event
#         if event_type in ["customer.subscription.created", "customer.subscription.updated"]:
#             # Handle subscription being created or changed (e.g., plan change, payment success)
#             subscription.stripe_subscription_id = sub_data.get("id")
#             subscription.status = sub_data.get("status") # e.g., 'active', 'trialing', 'past_due'
            
#             # Convert Stripe's timestamp to a Django datetime object
#             period_end_timestamp = sub_data.get("current_period_end")
#             if period_end_timestamp:
#                 subscription.current_period_end = timezone.datetime.fromtimestamp(period_end_timestamp)
#             else:
#                 subscription.current_period_end = None
            
#             # A canceled subscription might be "updated" to inactive, so clear canceled_at
#             subscription.canceled_at = None

#         elif event_type == "customer.subscription.deleted":
#             # Handle a subscription being canceled or ending after a trial
#             subscription.status = "canceled"
#             subscription.current_period_end = None # The subscription no longer has a billing period
#             subscription.canceled_at = timezone.now()

#         else:
#             # For debugging purposes, you can log unhandled events
#             print(f"Unhandled event type: {event_type}")

#         # Save the changes to the database and send a real-time update
#         subscription.save()
#         _send_subscription_update(subscription)

#     except Subscription.DoesNotExist:
#         # If we get a webhook for a customer that isn't in our DB,
#         # it's not a server error. Just acknowledge receipt to Stripe.
#         print(f"Webhook received for unknown customer: {stripe_customer_id}")
#         pass

#     # Acknowledge the event was received successfully
#     return HttpResponse(status=200)


import stripe
import json
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Subscription
from .serializers import SubscriptionSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

stripe.api_key = settings.STRIPE_SECRET_KEY

def _send_subscription_update(subscription):
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
    payload = request.body
    
    # === TEMPORARY CHANGE FOR TESTING ===
    event = json.loads(payload)
    # === END OF CHANGE ===

    event_type = event["type"]
    data_object = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")

            if not customer_id or not subscription_id:
                return HttpResponse(status=400, content="Missing customer or subscription ID.")

            stripe_sub = stripe.Subscription.retrieve(subscription_id)
            subscription = Subscription.objects.get(stripe_customer_id=customer_id)

            subscription.stripe_subscription_id = stripe_sub.id
            subscription.status = stripe_sub.status

            # === FIX: Use the correct field names from the Stripe object ===
            # For a new trial subscription, the end date is `trial_end`.
            if stripe_sub.trial_end:
                subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)
                subscription.trial_end = timezone.datetime.fromtimestamp(stripe_sub.trial_end)

            if stripe_sub.trial_start:
                subscription.trial_start = timezone.datetime.fromtimestamp(stripe_sub.trial_start)
            # =============================================================
            
            subscription.canceled_at = None
            subscription.save()
            _send_subscription_update(subscription)

        elif event_type == "customer.subscription.updated":
            # This block now needs to be smarter.
            subscription = Subscription.objects.get(stripe_subscription_id=data_object.get("id"))
            subscription.status = data_object.get("status")

            # === FIX: Handle both trial end and regular period end ===
            # The `data_object` here is a subscription object.
            period_end_ts = data_object.get("trial_end") or data_object.get("current_period_end")
            if period_end_ts:
                subscription.current_period_end = timezone.datetime.fromtimestamp(period_end_ts)
            # ========================================================

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
        print(f"Webhook received for unknown customer/subscription.")
        pass

    return HttpResponse(status=200)