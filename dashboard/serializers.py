from rest_framework import serializers
from django.contrib.auth.models import User
from subscription.models import Subscription
from ai.models import StoryProject
from .models import SiteSettings
from django.conf import settings
import stripe
from authentication.serializers import PasswordValidator
from authentication.models import UserProfile

stripe.api_key = settings.STRIPE_SECRET_KEY


class SubscriptionManagementSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    current_plan = serializers.CharField(source='get_plan_display')
    renewal_date = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    status = serializers.CharField()
    class Meta:
        model = Subscription
        fields = ['id', 'user_name', 'current_plan', 'renewal_date', 'payment_method', 'status']
    def get_user_name(self, obj):
        profile_picture_url = None
        if hasattr(obj.user, 'profile') and obj.user.profile.profile_picture and hasattr(obj.user.profile.profile_picture, 'url'):
            if settings.USE_S3_STORAGE:
                profile_picture_url = obj.user.profile.profile_picture.url
            else:
                profile_picture_url = f"{settings.BACKEND_BASE_URL}{obj.user.profile.profile_picture.url}"
        return {"photo": profile_picture_url, "name": obj.user.get_full_name(), "email": obj.user.email}
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
            return {"cardType": card.brand.title(), "transactionId": f"**** {card.last4}"}
        except Exception:
            return None
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        return {'id': ret['id'], 'User Name': ret['user_name'], 'Current Plan': ret['current_plan'],
                'Renewal Date': ret['renewal_date'], 'Payment Method': ret['payment_method'], 'status': ret['status']}

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

class DashboardUserSerializer(serializers.ModelSerializer):
    plan = serializers.CharField(source='subscription.get_plan_display', read_only=True, default='Free')
    profile_picture_url = serializers.SerializerMethodField()
    date = serializers.DateTimeField(source='date_joined', format='%b %d, %Y')
    name = serializers.CharField(source='username')
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


class AdminProfileSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='profile.phone_number', read_only=True)
    profile_picture_url = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone_number', 'profile_picture_url']
    def get_profile_picture_url(self, obj):
        if hasattr(obj, 'profile') and obj.profile.profile_picture and hasattr(obj.profile.profile_picture, 'url'):
            if settings.USE_S3_STORAGE:
                return obj.profile.profile_picture.url
            return f"{settings.BACKEND_BASE_URL}{obj.profile.profile_picture.url}"
        return None

class AdminProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    def validate_email(self, value):
        user = self.context['request'].user
        if User.objects.filter(email=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email address is already in use by another account.")
        return value
    def update(self, instance, validated_data):
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.username = validated_data.get('email', instance.username)
        instance.save()
        profile, created = UserProfile.objects.get_or_create(user=instance)
        profile.phone_number = validated_data.get('phone_number', profile.phone_number)
        if 'profile_picture' in validated_data:
            profile.profile_picture = validated_data.get('profile_picture')
        profile.save()
        return instance

class AdminChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Your current password is not correct.")
        return value
    def validate(self, data):
        user = self.context['request'].user
        if user.check_password(data['new_password']):
            raise serializers.ValidationError({"new_password": "New password cannot be the same as the old password."})
        return data