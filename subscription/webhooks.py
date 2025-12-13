import logging
import json
import datetime
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Subscription, ProcessedWebhookEvent
from .serializers import SubscriptionSerializer

logger = logging.getLogger(__name__)
User = get_user_model()

RC_PLAN_MAPPING = {
    "rc_entitlement_creator": "creator", 
    "rc_entitlement_master": "master",
}

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

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def revenuecat_webhook(request):
    auth_header = request.headers.get("Authorization")
    expected_header = settings.REVENUECAT_WEBHOOK_AUTH_HEADER
    
    if expected_header and auth_header != expected_header:
        logger.warning("RevenueCat Webhook: Invalid Authorization Header")
        return HttpResponseForbidden("Invalid Authorization")

    try:
        payload = json.loads(request.body)
        event = payload.get('event', {})
        event_id = event.get('id')
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    if not event_id:
        return HttpResponse(status=200)

    try:
        ProcessedWebhookEvent.objects.create(event_id=event_id)
    except IntegrityError:
        logger.info(f"RevenueCat event {event_id} already processed.")
        return HttpResponse(status=200)

    app_user_id = event.get('app_user_id')
    
    try:
        user_id = int(app_user_id)
        user = User.objects.get(id=user_id)
    except (ValueError, TypeError, User.DoesNotExist):
        logger.error(f"RevenueCat Webhook: Could not find Django User for app_user_id='{app_user_id}'")
        return HttpResponse(status=200)

    type = event.get('type')
    entitlement_ids = event.get('entitlement_ids', [])
    expiration_at_ms = event.get('expiration_at_ms')
    
    subscription, _ = Subscription.objects.get_or_create(user=user)
    
    new_plan = "trial" 
    
    if "rc_entitlement_master" in entitlement_ids:
        new_plan = "master"
    elif "rc_entitlement_creator" in entitlement_ids:
        new_plan = "creator"
        
    if type in ['INITIAL_PURCHASE', 'RENEWAL', 'UNCANCELLATION', 'PRODUCT_CHANGE']:
        subscription.status = 'active'
        subscription.plan = new_plan
        if expiration_at_ms:
            subscription.current_period_end = datetime.datetime.fromtimestamp(expiration_at_ms / 1000.0, tz=timezone.utc)
        
    elif type in ['CANCELLATION']:
        pass
        
    elif type in ['EXPIRATION']:
        subscription.status = 'expired'
        subscription.plan = 'trial'
        subscription.current_period_end = timezone.now()

    subscription.revenue_cat_id = app_user_id
    subscription.save()
    
    logger.info(f"Updated subscription for User {user.id} to {subscription.plan} via RevenueCat.")
    _send_subscription_update(subscription)

    return HttpResponse(status=200)