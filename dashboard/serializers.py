from rest_framework import serializers
from django.contrib.auth.models import User
from subscription.models import Subscription
from ai.models import StoryProject
from .models import SiteSettings
from django.conf import settings
from authentication.serializers import PasswordValidator
from authentication.models import UserProfile
from django.utils.translation import gettext as _

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
        profile_picture_url = obj.user.profile.profile_picture_url if hasattr(obj.user, 'profile') else None
        return {"photo": profile_picture_url, "name": obj.user.get_full_name(), "email": obj.user.email}
    def get_renewal_date(self, obj):
        date_to_format = obj.trial_end if obj.status == 'trialing' else obj.current_period_end
        return date_to_format.strftime('%b %d, %Y') if date_to_format else None
    def get_payment_method(self, obj):
        return {"cardType": "Mobile Store", "transactionId": "In-App"}
        
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
    profile_picture_url = serializers.CharField(source='profile.profile_picture_url', read_only=True) 
    date = serializers.DateTimeField(source='date_joined', format='%b %d, %Y')
    name = serializers.CharField(source='username')
    class Meta:
        model = User
        fields = ['id', 'profile_picture_url', 'name', 'email', 'date', 'plan']

class DashboardStorySerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='theme')
    creator = serializers.CharField(source='user.username', read_only=True)
    date = serializers.DateTimeField(source='created_at', format='%b %d, %Y')
    status = serializers.SerializerMethodField()
    class Meta:
        model = StoryProject
        fields = ['id', 'title', 'creator', 'date', 'status']
    def get_status(self, obj):
        return 'Published' if obj.status == 'done' else 'Pending'


class AdminProfileSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='profile.phone_number', read_only=True)
    profile_picture_url = serializers.CharField(source='profile.profile_picture_url', read_only=True) 
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone_number', 'profile_picture_url']

class AdminProfileUpdateSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='profile.phone_number', required=False, allow_blank=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'profile_picture']

    def validate_email(self, value):
        user = self.context['request'].user
        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(_("This email address is already in use by another account."))
        return value

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {}) 
        
        has_picture_update = 'profile_picture' in validated_data
        profile_picture = validated_data.pop('profile_picture', None)

        if 'email' in validated_data:
            instance.username = validated_data['email']
        
        instance = super().update(instance, validated_data)

        profile, created = UserProfile.objects.get_or_create(user=instance)
        
        if 'phone_number' in profile_data:
            profile.phone_number = profile_data['phone_number']
            
        if has_picture_update:
            profile.profile_picture = profile_picture
            
        profile.save()
        
        return instance

class AdminChangePasswordSerializer(serializers.Serializer):
    # current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[PasswordValidator.validate_password_strength])
    
    # def validate_current_password(self, value):
    #     user = self.context['request'].user
    #     if not user.check_password(value):
    #         raise serializers.ValidationError(_("Your current password is not correct."))
    #     return value
    
    def validate(self, data):
        user = self.context['request'].user
        if user.check_password(data['new_password']):
            raise serializers.ValidationError({"new_password": _("New password cannot be the same as the old password.")})
        return data