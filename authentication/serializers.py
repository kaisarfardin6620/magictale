import re
import hashlib
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.urls import reverse
from django.template.loader import render_to_string
from rest_framework import serializers
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from subscription.models import Subscription
from .models import UserProfile, AuthToken, PasswordHistory, UserActivityLog, OnboardingStatus
from .utils import send_email
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from fcm_django.models import FCMDevice

class PasswordValidator:
    @staticmethod
    def validate_breached_password(password):
        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            response = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=2)
            return suffix in response.text
        except requests.RequestException:
            return False

    @staticmethod
    def validate_password_strength(password):
        if len(password) < 10:
            raise serializers.ValidationError("Password must be at least 10 characters long.")
        if not re.search(r"[A-Z]", password):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", password):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+=\-{}[\]|\\:;\"'<,>.?/]", password):
            raise serializers.ValidationError("Password must contain at least one special character.")

class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    email = serializers.EmailField(required=True)
    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'], email=validated_data['email'],
            password=validated_data['password'], is_active=False
        )
        UserProfile.objects.create(user=user)
        return user

class MyTokenObtainPairSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    fcm_token = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        fcm_token = attrs.get('fcm_token') 
        if not email or not password:
            raise serializers.ValidationError('Must include "email" and "password".')
        try:
            user_obj = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('No active account found with the given credentials')
        user = authenticate(request=self.context.get('request'), username=user_obj.username, password=password)
        if not user:
            raise serializers.ValidationError('No active account found with the given credentials')

        if fcm_token:
            user_agent = self.context['request'].META.get('HTTP_USER_AGENT', '').lower()
            if 'android' in user_agent:
                device_type = 'android'
            elif 'iphone' in user_agent or 'ipad' in user_agent:
                device_type = 'ios'
            else:
                device_type = 'web'

            FCMDevice.objects.update_or_create(
                registration_id=fcm_token,
                defaults={
                    'user': user,
                    'active': True,
                    'type': device_type
                }
            )

        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token
        access_token['is_staff'] = user.is_staff
        access_token['username'] = user.username
        try:
            subscription = user.subscription
            access_token['plan'] = subscription.plan
            access_token['subscription_status'] = subscription.status
        except (AttributeError, User.subscription.RelatedObjectDoesNotExist):
            access_token['plan'] = None
            access_token['subscription_status'] = 'inactive'
        data = {'refresh': str(refresh), 'access': str(access_token)}
        return data

class ProfileSerializer(serializers.ModelSerializer):
    subscription_active = serializers.SerializerMethodField()
    current_plan = serializers.SerializerMethodField()
    trial_end_date = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    class Meta:
        model = UserProfile
        fields = [
            'profile_picture', 'phone_number', 'language', 'allow_push_notifications',
            'subscription_active', 'current_plan', 'trial_end_date'
        ]
    def get_profile_picture(self, obj):
        if obj.profile_picture and hasattr(obj.profile_picture, 'url'):
            if settings.USE_S3_STORAGE:
                return obj.profile_picture.url
            return f"{settings.BACKEND_BASE_URL}{obj.profile_picture.url}"
        return None
    def get_subscription_active(self, obj):
        try:
            return obj.user.subscription.status in ['active', 'trialing']
        except (Subscription.DoesNotExist, AttributeError):
            return False
    def get_current_plan(self, obj):
        try:
            return obj.user.subscription.get_plan_display()
        except (Subscription.DoesNotExist, AttributeError):
            return None
    def get_trial_end_date(self, obj):
        try:
            return obj.user.subscription.trial_end
        except (Subscription.DoesNotExist, AttributeError):
            return None

class UnifiedProfileUpdateSerializer(serializers.Serializer):
    user_name = serializers.CharField(max_length=301, required=False)
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    new_email = serializers.EmailField(required=False, write_only=True)
    new_password = serializers.CharField(style={'input_type': 'password'}, write_only=True, required=False, validators=[PasswordValidator.validate_password_strength])
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    allow_push_notifications = serializers.BooleanField(required=False)
    def validate_current_password(self, value):
        user = self.context['request'].user
        if not check_password(value, user.password):
            raise serializers.ValidationError("Your current password is not correct.")
        return value
    def validate_new_email(self, value):
        user = self.context['request'].user
        if User.objects.filter(email=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email address is already in use by another account.")
        return value
    def validate(self, data):
        if 'new_password' in data and 'confirm_new_password' in data:
            if data['new_password'] != data['confirm_new_password']:
                raise serializers.ValidationError({"confirm_new_password": "The two new password fields didn't match."})
        elif 'new_password' in data:
             raise serializers.ValidationError({"confirm_new_password": "You must confirm your new password."})
        if 'new_password' in data and 'current_password' in data:
            user = self.context['request'].user
            if check_password(data['new_password'], user.password):
                raise serializers.ValidationError({"new_password": "New password cannot be the same as the old password."})
        return data
    def update(self, instance, validated_data):
        user = instance.user
        profile = instance
        if 'user_name' in validated_data:
            full_name = validated_data.get('user_name', '').strip()
            name_parts = full_name.split(' ', 1)
            user.first_name = name_parts[0]
            user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        else:
            user.first_name = validated_data.get('first_name', user.first_name)
            user.last_name = validated_data.get('last_name', user.last_name)
        new_email = validated_data.get('new_email')
        if new_email and new_email.lower() != user.email.lower():
            user.email = new_email
            user.username = new_email
        if 'new_password' in validated_data and 'current_password' in validated_data:
            user.set_password(validated_data['new_password'])
            PasswordHistory.objects.create(user=user, password_hash=user.password)
            OutstandingToken.objects.filter(user=user).delete()
        user.save()
        profile.phone_number = validated_data.get('phone_number', profile.phone_number)
        profile.allow_push_notifications = validated_data.get('allow_push_notifications', profile.allow_push_notifications)
        if 'profile_picture' in validated_data:
            profile.profile_picture = validated_data.get('profile_picture')
        profile.save()
        return profile

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
class PasswordResetFormSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    confirm_password = serializers.CharField(write_only=True, required=True)
    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("The two password fields didn't match.")
        return data

class EmailChangeConfirmSerializer(serializers.Serializer):
    token = serializers.UUIDField()
class ResendVerificationSerializer(serializers.Serializer):
    username = serializers.CharField()
class UserActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivityLog
        fields = ['activity_type', 'timestamp', 'ip_address', 'user_agent']
class LanguagePreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['language']
    def validate_language(self, value):
        if len(value) > 10:
             raise serializers.ValidationError("Language code is too long.")
        return value