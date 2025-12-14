import requests
import datetime
from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Subscription
from .serializers import SubscriptionSerializer

class SubscriptionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

    @action(detail=False, methods=["get"], url_path='status')
    def status(self, request):
        subscription, created = Subscription.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(subscription)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path='sync')
    def sync_subscription(self, request):
        user = request.user
        app_user_id = str(user.id)
        
        headers = {
            "Authorization": f"Bearer {settings.REVENUECAT_API_KEY}",
            "Content-Type": "application/json",
            "X-Platform": "android"
        }
        
        url = f"https://api.revenuecat.com/v1/subscribers/{app_user_id}"
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                subscriber = data.get('subscriber', {})
                entitlements = subscriber.get('entitlements', {})
                
                subscription, _ = Subscription.objects.get_or_create(user=user)
                
                active_plan = None
                max_expiration = None

                if "rc_entitlement_master" in entitlements:
                    ent = entitlements["rc_entitlement_master"]
                    expires_date_str = ent.get("expires_date")
                    if expires_date_str:
                        expires_date = datetime.datetime.fromisoformat(expires_date_str.replace('Z', '+00:00'))
                        if expires_date > timezone.now():
                            active_plan = "master"
                            max_expiration = expires_date
                    else:
                        active_plan = "master"

                if not active_plan and "rc_entitlement_creator" in entitlements:
                    ent = entitlements["rc_entitlement_creator"]
                    expires_date_str = ent.get("expires_date")
                    if expires_date_str:
                        expires_date = datetime.datetime.fromisoformat(expires_date_str.replace('Z', '+00:00'))
                        if expires_date > timezone.now():
                            active_plan = "creator"
                            max_expiration = expires_date
                    else:
                        active_plan = "creator"

                if active_plan:
                    subscription.status = 'active'
                    subscription.plan = active_plan
                    if max_expiration:
                        subscription.current_period_end = max_expiration
                else:
                    if subscription.status == 'active':
                        subscription.status = 'expired'
                        subscription.plan = 'trial'
                        subscription.current_period_end = timezone.now()
                
                subscription.revenue_cat_id = app_user_id
                subscription.save()
                
                return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_200_OK)
            
            elif response.status_code == 404:
                return Response({"detail": "User not found in RevenueCat"}, status=status.HTTP_404_NOT_FOUND)
            
            else:
                return Response({"detail": "Failed to connect to RevenueCat"}, status=status.HTTP_502_BAD_GATEWAY)

        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)