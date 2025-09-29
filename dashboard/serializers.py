from rest_framework import serializers
from django.contrib.auth.models import User
from subscription.models import Subscription
from .models import SiteSettings
from django.conf import settings
import stripe

# Set the API key for Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

class SubscriptionManagementSerializer(serializers.ModelSerializer):
    # --- THIS IS THE FIX ---
    # Use valid Python variable names (with underscores).
    # The `source` argument points to the method that will provide the data.
    # The serializer will automatically rename the output key from 'user_name' to 'User Name'.
    user_name = serializers.SerializerMethodField(source='get_User_Name')
    current_plan = serializers.CharField(source='get_plan_display')
    renewal_date = serializers.SerializerMethodField(source='get_Renewal_Date')
    payment_method = serializers.SerializerMethodField(source='get_Payment_Method')

    # We also need to add a 'status' field.
    status = serializers.CharField()
    
    # We will rename the output fields in the to_representation method.
    
    class Meta:
        model = Subscription
        # Use the valid Python field names here.
        fields = [
            'id',
            'user_name',
            'current_plan',
            'renewal_date',
            'payment_method',
            'status'
        ]

    # --- RENAME THE METHODS TO MATCH THE `source` ARGUMENTS ---
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
        date_to_format = None
        if obj.status == 'trialing':
            date_to_format = obj.trial_end
        else:
            date_to_format = obj.current_period_end
        
        if date_to_format:
            return date_to_format.strftime('%b %d, %Y')
        return None

    def get_payment_method(self, obj):
        if not obj.stripe_customer_id:
            return None
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=obj.stripe_customer_id,
                type="card",
            )
            if not payment_methods.data:
                return None
            
            card = payment_methods.data[0].card
            return {
                "cardType": card.brand.title(),
                "transactionId": f"**** {card.last4}"
            }
        except Exception:
            return None

    # --- ADD THIS METHOD TO RENAME THE OUTPUT KEYS ---
    def to_representation(self, instance):
        """
        Convert `obj` into a dictionary representation with custom key names.
        """
        ret = super().to_representation(instance)
        # This renames the keys to match the frontend's expected format with spaces.
        return {
            'id': ret['id'],
            'User Name': ret['user_name'],
            'Current Plan': ret['current_plan'],
            'Renewal Date': ret['renewal_date'],
            'Payment Method': ret['payment_method'],
            'status': ret['status']
        }


class SiteSettingsSerializer(serializers.ModelSerializer):
    # ... (This class remains unchanged)
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