from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'body', 'read', 'created_at', 'data']
        read_only_fields = ['id', 'title', 'body', 'created_at', 'data']