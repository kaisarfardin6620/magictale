from rest_framework import serializers
from django.contrib.auth.models import User
from subscription.models import Subscription
from ai.models import StoryProject
from .models import SiteSettings
from django.conf import settings
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

class SubscriptionManagementSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    current_plan = serializers.CharField(source='get_plan_display')
    renewal_date = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    status = serializers.CharField()

    class Meta:
        model = Subscription
        fields = [
            'id', 'user_name', 'current_plan', 'renewal_date', 'payment_method', 'status'
        ]

    def get_user_name(self, obj):
        profile_picture_url = None
        if hasattr(obj.user, 'profile') and obj.user.profile.profile_picture and hasattr(obj.user.profile.profile_picture, 'url'):
            if settings.USE_S3_STORAGE:
                profile_picture_url = obj.user.profile.profile_picture.url
            else:
                profile_picture_url = f"{settings.BACKEND_BASE_URL}{obj.user.profile.profile_picture.url}"
        return {
            "photo": profile_picture_url,
            "name": obj.user.get_full_name(),
            "email": obj.user.email
        }

    def get_renewal_date(self, obj):
        date_to_format = obj.trial_end if obj.status == 'trialing' else obj.current_period_end
        return date_to_format.strftime('%b %d, %Y') if date_to_format else None

    def get_payment_method(self, obj):
        if not obj.stripe_customer_id:
            return None
        try:
            payment_methods = stripe.PaymentMethod.list(customer=obj.stripe_customer_id, type="card")
            if not payment_methods.data:
                return None
            card = payment_methods.data[0].card
            return {
                "cardType": card.brand.title(),
                "transactionId": f"**** {card.last4}"
            }
        except Exception:
            return None

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        return {
            'id': ret['id'],
            'User Name': ret['user_name'],
            'Current Plan': ret['current_plan'],
            'Renewal Date': ret['renewal_date'],
            'Payment Method': ret['payment_method'],
            'status': ret['status']
        }

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

# === ADD THESE NEW SERIALIZERS ===

class DashboardUserSerializer(serializers.ModelSerializer):
    plan = serializers.CharField(source='subscription.get_plan_display', read_only=True, default='Free')
    profile_picture_url = serializers.SerializerMethodField()
    date = serializers.DateTimeField(source='date_joined', format='%b %d, %Y')
    name = serializers.CharField(source='get_full_name')

    class Meta:
        model = User
        fields = ['id', 'profile_picture_url', 'name', 'email', 'date', 'plan']
    
    def get_profile_picture_url(self, obj):
        if hasattr(obj, 'profile') and obj.profile.profile_picture and hasattr(obj.profile.profile_picture, 'url'):
            if settings.USE_S3_STORAGE:
                return obj.profile.profile_picture.url
            return f"{settings.BACKEND_BASE_URL}{obj.profile.profile_picture.url}"
        return None

class DashboardStorySerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='theme')
    creator = serializers.CharField(source='user.get_full_name', read_only=True)
    date = serializers.DateTimeField(source='created_at', format='%b %d, %Y')
    status = serializers.SerializerMethodField()

    class Meta:
        model = StoryProject
        fields = ['id', 'title', 'creator', 'date', 'status']
    
    def get_status(self, obj):
        return 'Published' if obj.status == 'done' else 'Pending'