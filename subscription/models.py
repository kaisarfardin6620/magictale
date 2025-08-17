from django.conf import settings
from django.db import models

class Subscription(models.Model):
    PLAN_CHOICES = [
        ("creator", "Story Creator"),
        ("master", "Story Master"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription"
    )
    stripe_customer_id = models.CharField(max_length=255)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)

    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    status = models.CharField(max_length=50, default="inactive")  # trialing, active, canceled
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.plan} ({self.status})"