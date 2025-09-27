from rest_framework import serializers
from django.contrib.auth.models import User
from subscription.models import Subscription
from .models import SiteSettings
from django.conf import settings
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

class UserForAdminSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name')
    profile_picture_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'profile_picture_url']

    def get_profile_picture_url(self, obj):
        if hasattr(obj, 'profile') and obj.profile.profile_picture and hasattr(obj.profile.profile_picture, 'url'):
            if settings.USE_S3_STORAGE:
                return obj.profile.profile_picture.url
            return f"{settings.BACKEND_BASE_URL}{obj.profile.profile_picture.url}"
        return None

class SubscriptionManagementSerializer(serializers.ModelSerializer):
    user = UserForAdminSerializer(read_only=True)
    plan_display = serializers.CharField(source='get_plan_display')
    payment_method = serializers.SerializerMethodField()
    renewal_date = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ['id', 'user', 'plan_display', 'status', 'renewal_date', 'payment_method']

    def get_renewal_date(self, obj):
        if obj.status == 'trialing':
            return obj.trial_end
        return obj.current_period_end

    def get_payment_method(self, obj):
        if not obj.stripe_customer_id:
            return "Not available"
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=obj.stripe_customer_id,
                type="card",
            )
            if not payment_methods.data:
                return "No card on file"
            
            card = payment_methods.data[0].card
            return f"{card.brand.title()} ****{card.last4}"
        except Exception:
            return "Could not retrieve"


class SiteSettingsSerializer(serializers.ModelSerializer):
    application_logo_url = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = ['application_name', 'application_logo', 'application_logo_url', 'default_language', 'timezone']
        read_only_fields = ['application_logo_url']
        extra_kwargs = {'application_logo': {'write_only': True, 'required': False}}

    def get_application_logo_url(self, obj):
        if obj.application_logo and hasattr(obj.application_logo, 'url'):
            if settings.USE_S3_STORAGE:
                return obj.application_logo.url
            return f"{settings.BACKEND_BASE_URL}{obj.application_logo.url}"
        return None