from rest_framework import serializers
from .models import DeviceToken

class DeviceTokenSerializer(serializers.ModelSerializer):
    """
    Serializer for the DeviceToken model.
    """
    class Meta:
        model = DeviceToken
        fields = ["id", "token"]