import re
import hashlib
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from rest_framework import serializers
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from subscription.models import Subscription
from .models import UserProfile, AuthToken, PasswordHistory, UserActivityLog
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
from notifications.tasks import create_and_send_notification_task
from django.utils.translation import gettext as _
from datetime import datetime

class PasswordValidator:
    @staticmethod
    def validate_breached_password(password):
        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            response = requests.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=2.0)
            return suffix in response.text
        except requests.RequestException:
            return False

    @staticmethod
    def validate_password_strength(password):
        has_length = len(password) >= 10
        has_upper = re.search(r"[A-Z]", password)
        has_lower = re.search(r"[a-z]", password)
        has_digit = re.search(r"\d", password)
        has_special = re.search(r"[!@#$%^&*()_+=\-{}[\]|\\:;\"'<,>.?/]", password)

        if not (has_length and has_upper and has_lower and has_digit and has_special):
            raise serializers.ValidationError(
                _("Password must contain at least 10 characters, including an uppercase letter, a lowercase letter, a number, and a special character.")
            )

class SignupSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("This email is already in use."))
        return value

    def create(self, validated_data):
        full_name = validated_data.pop('full_name').strip()
        email = validated_data['email']
        password = validated_data['password']

        if " " in full_name:
            first_name, last_name = full_name.split(" ", 1)
        else:
            first_name, last_name = full_name, ""

        user = User.objects.create_user(
            username=email, 
            email=email,
            password=password, 
            first_name=first_name,
            last_name=last_name,
            is_active=False
        )
        return user

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'] = serializers.EmailField()
        if 'username' in self.fields:
            del self.fields['username']

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['is_staff'] = user.is_staff
        token['username'] = user.username
        try:
            subscription = user.subscription
            token['plan'] = subscription.plan
            token['subscription_status'] = subscription.status
        except (AttributeError, User.subscription.RelatedObjectDoesNotExist):
            token['plan'] = None
            token['subscription_status'] = 'inactive'
        return token

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email:
            raise serializers.ValidationError(_('Email address is required to log in.'), code='authorization')

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise AuthenticationFailed(_("No account found with this email. Please check your email and try again."))

        if not user.check_password(password):
            raise AuthenticationFailed(_("The password you entered is incorrect. Please try again."))

        if not user.is_active:
            raise AuthenticationFailed(_("This account is inactive. Please verify your email before logging in."))

        self.user = user

        refresh = self.get_token(self.user)
        data = {
            'id': self.user.id,
            'email': self.user.email,
            'full_name': f"{self.user.first_name} {self.user.last_name}".strip(),
            'token': str(refresh.access_token),
            'refresh_token': str(refresh)
        }

        return data

class FCMDeviceSerializer(serializers.Serializer):
    registration_id = serializers.CharField(required=True)
    type = serializers.ChoiceField(choices=['ios', 'android', 'web'], required=False, default='web')

class ProfileSerializer(serializers.ModelSerializer):
    subscription_active = serializers.SerializerMethodField()
    current_plan = serializers.SerializerMethodField()
    trial_end_date = serializers.SerializerMethodField()
    profile_picture = serializers.CharField(source='profile_picture_url', read_only=True) 
    class Meta:
        model = UserProfile
        fields = [
            'profile_picture', 'phone_number', 'allow_push_notifications',
            'subscription_active', 'current_plan', 'trial_end_date'
        ]
    def get_subscription_active(self, obj) -> bool:
        try:
            return obj.user.subscription.status in ['active', 'trialing']
        except (Subscription.DoesNotExist, AttributeError):
            return False
    def get_current_plan(self, obj) -> str | None:
        try:
            return obj.user.subscription.get_plan_display()
        except (Subscription.DoesNotExist, AttributeError):
            return None
    def get_trial_end_date(self, obj) -> datetime | None:
        try:
            return obj.user.subscription.trial_end
        except (Subscription.DoesNotExist, AttributeError):
            return None

class UnifiedProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=301, required=False)
    new_email = serializers.EmailField(required=False, write_only=True)
    new_password = serializers.CharField(style={'input_type': 'password'}, write_only=True, required=False, validators=[PasswordValidator.validate_password_strength])
    profile_picture = serializers.ImageField(required=False, allow_null=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    allow_push_notifications = serializers.BooleanField(required=False)

    def validate_new_email(self, value):
        user = self.context['request'].user
        if User.objects.filter(email=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(_("This email address is already in use by another account."))
        return value

    def validate(self, data):
        if 'new_password' in data:
            user = self.context['request'].user
            if check_password(data['new_password'], user.password):
                raise serializers.ValidationError({"new_password": _("New password cannot be the same as the old password.")})
        return data

    def update(self, instance, validated_data):
        user = instance.user
        profile = instance
        
        if 'full_name' in validated_data:
            full_name = validated_data.get('full_name', '').strip()
            if " " in full_name:
                first_name, last_name = full_name.split(" ", 1)
            else:
                first_name, last_name = full_name, ""
            user.first_name = first_name
            user.last_name = last_name
        
        new_email = validated_data.get('new_email')
        if new_email and new_email.lower() != user.email.lower():
            user.email = new_email
            user.username = new_email
            
        if 'new_password' in validated_data:
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
            raise serializers.ValidationError(_("The two password fields didn't match."))
        return data

class EmailChangeConfirmSerializer(serializers.Serializer):
    token = serializers.UUIDField()
class ResendVerificationSerializer(serializers.Serializer):
    username = serializers.CharField()
class UserActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivityLog
        fields = ['activity_type', 'timestamp', 'ip_address', 'user_agent']