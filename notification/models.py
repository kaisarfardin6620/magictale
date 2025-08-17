from django.db import models
from django.conf import settings

class DeviceToken(models.Model):
    """
    Stores Firebase Cloud Messaging (FCM) device registration tokens.
    Each token is unique to a user's device and used to send push notifications.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens"
    )
    token = models.CharField(max_length=255, unique=True)
    device_type = models.CharField(max_length=20, blank=True, null=True)  # iOS / Android / Web
    last_used_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.device_type or 'Unknown'}"