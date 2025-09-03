import re
import hashlib
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, make_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from subscription.models import Subscription
from .models import UserProfile, AuthToken, PasswordHistory, UserActivityLog
from .models import OnboardingStatus


class PasswordValidator:
    @staticmethod
    def validate_breached_password(password):
        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            response = requests.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                timeout=2
            )
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
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            is_active=False
        )
        UserProfile.objects.create(user=user)
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            return value
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    reset_id = serializers.UUIDField(required=True)
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[PasswordValidator.validate_password_strength, PasswordValidator.validate_breached_password]
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True
    )

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("The two password fields didn't match.")
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])

    def validate_new_password(self, value):
        if PasswordValidator.validate_breached_password(value):
            raise serializers.ValidationError("This password has been found in a data breach. Please choose a different one.")
        return value

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not check_password(value, user.password):
            raise serializers.ValidationError("Incorrect password.")
        return value

    def validate(self, data):
        user = self.context['request'].user
        if check_password(data['new_password'], user.password):
            raise serializers.ValidationError("New password cannot be the same as the old password.")

        password_histories = PasswordHistory.objects.filter(user=user).order_by('-created_at')[:10]
        for history in password_histories:
            if check_password(data['new_password'], history.password_hash):
                raise serializers.ValidationError("You cannot reuse a recent password.")
        return data


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        try:
            subscription = user.subscription
            token['plan'] = subscription.plan
            token['subscription_status'] = subscription.status
        except AttributeError:
            token['plan'] = None
            token['subscription_status'] = 'inactive'
        return token


class ProfileSerializer(serializers.ModelSerializer):
    subscription_active = serializers.SerializerMethodField()
    current_plan = serializers.SerializerMethodField()
    trial_end_date = serializers.SerializerMethodField()
    language = serializers.CharField() # <-- ADD THIS LINE

    class Meta:
        model = UserProfile
        fields = [
            'profile_picture',
            'phone_number',
            'language', 
            'allow_push_notifications',
            'subscription_active',
            'current_plan',
            'trial_end_date'
        ]

    def get_subscription_active(self, obj):
        try:
            return obj.user.subscription.status in ['active', 'trialing']
        except Subscription.DoesNotExist:
            return False

    def get_current_plan(self, obj):
        try:
            return obj.user.subscription.get_plan_display()
        except Subscription.DoesNotExist:
            return None

    def get_trial_end_date(self, obj):
        try:
            return obj.user.subscription.trial_end
        except Subscription.DoesNotExist:
            return None


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['phone_number']


class ProfilePictureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['profile_picture']


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField()

    def validate_new_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email address is already in use.")
        return value


class EmailChangeConfirmSerializer(serializers.Serializer):
    token = serializers.UUIDField()


class ResendVerificationSerializer(serializers.Serializer):
    username = serializers.CharField()


class UserActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivityLog
        fields = ['activity_type', 'timestamp', 'ip_address', 'user_agent']


class FullNameUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']


class OnboardingStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingStatus
        fields = [
            'id', 'child_name', 'age', 'pronouns', 'favorite_animal',
            'favorite_color', 'onboarding_complete'
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        user = self.context['request'].user
        onboarding_status, created = OnboardingStatus.objects.update_or_create(
            user=user,
            defaults=validated_data
        )
        return onboarding_status
class LanguagePreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['language']

    def validate_language(self, value):
        if len(value) > 10:
             raise serializers.ValidationError("Language code is too long.")
        return value