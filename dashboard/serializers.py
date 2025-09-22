from rest_framework import serializers
from django.contrib.auth.models import User
from subscription.models import Subscription
from .models import SiteSettings
from django.conf import settings

class UserForAdminSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name')
    profile_picture_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'profile_picture_url']

    def get_profile_picture_url(self, obj):
        if hasattr(obj, 'profile') and obj.profile.profile_picture:
            return f"{settings.BACKEND_BASE_URL}{obj.profile.profile_picture.url}"
        return None

class SubscriptionManagementSerializer(serializers.ModelSerializer):
    user = UserForAdminSerializer(read_only=True)
    plan_display = serializers.CharField(source='get_plan_display')

    class Meta:
        model = Subscription
        fields = ['id', 'user', 'plan', 'plan_display', 'status', 'current_period_end', 'trial_end']

class SiteSettingsSerializer(serializers.ModelSerializer):
    application_logo_url = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = ['application_name', 'application_logo', 'application_logo_url', 'default_language', 'timezone']
        read_only_fields = ['application_logo_url']
        extra_kwargs = {'application_logo': {'write_only': True, 'required': False}}

    def get_application_logo_url(self, obj):
        if obj.application_logo and hasattr(obj.application_logo, 'url'):
            return f"{settings.BACKEND_BASE_URL}{obj.application_logo.url}"
        return None