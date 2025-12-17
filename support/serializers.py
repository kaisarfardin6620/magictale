from rest_framework import serializers
from .models import UserReport, LegalDocument
from django.conf import settings
from django.utils.translation import gettext as _

class UserReportSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    screenshot_url = serializers.SerializerMethodField()

    class Meta:
        model = UserReport
        fields = ['id', 'username', 'email', 'message', 'screenshot', 'screenshot_url', 'created_at', 'is_resolved']
        read_only_fields = ['id', 'created_at', 'is_resolved', 'screenshot_url']
        extra_kwargs = {
            'screenshot': {'required': False, 'write_only': True},
            'message': {'required': False}
        }

    def get_screenshot_url(self, obj):
        if obj.screenshot and hasattr(obj.screenshot, 'url'):
            if settings.USE_S3_STORAGE:
                return obj.screenshot.url
            return f"{settings.BACKEND_BASE_URL}{obj.screenshot.url}"
        return None

    def validate(self, data):
        if not data.get('message') and not data.get('screenshot'):
            raise serializers.ValidationError(_("Please provide either a message or a screenshot."))
        return data

class LegalDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalDocument
        fields = ['id', 'doc_type', 'title', 'content', 'last_updated']