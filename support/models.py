from django.db import models
from django.conf import settings

class UserReport(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    message = models.TextField(blank=True, null=True)
    screenshot = models.ImageField(upload_to='support_screenshots/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"Report {self.id} by {self.user.username}"

class LegalDocument(models.Model):
    DOC_TYPES = (
        ('privacy_policy', 'Privacy Policy'),
        ('terms_conditions', 'Terms and Conditions'),
    )
    doc_type = models.CharField(max_length=50, choices=DOC_TYPES, unique=True)
    title = models.CharField(max_length=200)
    content = models.JSONField(default=dict)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_doc_type_display()