from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import RegexValidator
import uuid
from django.conf import settings

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r"^\+?[1-9]\d{1,14}$",
                message="Phone number must be in E.164 format: '+1234567890'"
            )
        ]
    )

    language = models.CharField(max_length=10, default='en', blank=True)
    email_verified = models.BooleanField(default=False)
    allow_push_notifications = models.BooleanField(default=True)
    parental_consent = models.BooleanField(default=False)
    accepted_terms = models.BooleanField(default=False)
    used_art_styles = models.TextField(
        blank=True, default="",
        help_text="Comma-separated list of art style IDs used by the user during their trial."
    )
    used_narrator_voices = models.TextField(
        blank=True, default="",
        help_text="Comma-separated list of voice IDs used by the user during their trial."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username

    @property
    def profile_picture_url(self):
        if self.profile_picture and hasattr(self.profile_picture, 'url'):
            if settings.USE_S3_STORAGE:
                return self.profile_picture.url
            return f"{settings.BACKEND_BASE_URL}{self.profile_picture.url}"
        return None


class AuthToken(models.Model):
    TOKEN_TYPES = (
        ('signup', 'Signup Verification'),
        ('2fa', 'Two-Factor Authentication'),
        ('password_reset', 'Password Reset'),
        ('email_change', 'Email Change'),
        ('reactivation', 'Account Reactivation'),
        ('email_verification', 'Email Verification'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_tokens')
    token_type = models.CharField(max_length=20, choices=TOKEN_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    def __str__(self):
        return f"{self.user.username} - {self.token_type} Token"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            if self.token_type in ['signup', 'email_verification', 'reactivation']:
                self.expires_at = timezone.now() + timezone.timedelta(hours=24)
            elif self.token_type in ['password_reset', 'email_change']:
                self.expires_at = timezone.now() + timezone.timedelta(hours=1)
            elif self.token_type == '2fa':
                self.expires_at = timezone.now() + timezone.timedelta(minutes=15)
            else:
                self.expires_at = timezone.now() + timezone.timedelta(hours=24)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()


class PasswordHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_histories')
    password_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        histories = PasswordHistory.objects.filter(user=self.user).order_by('-created_at')
        if histories.count() > 10:
            oldest = PasswordHistory.objects.filter(user=self.user).order_by('created_at').first()
            if oldest:
                oldest.delete()


class UserActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    activity_type = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.activity_type} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class OnboardingStatus(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='onboarding_status')
    child_name = models.CharField(max_length=100, blank=True, null=True)
    age = models.PositiveIntegerField(blank=True, null=True)
    pronouns = models.CharField(max_length=50, blank=True, null=True)
    favorite_animal = models.CharField(max_length=100, blank=True, null=True)
    favorite_color = models.CharField(max_length=50, blank=True, null=True)
    onboarding_complete = models.BooleanField(default=False)

    def __str__(self):
        if self.child_name:
            return f"Hero Profile for '{self.child_name}' ({self.user.username})"
        return f"{self.user.username}'s (empty) Hero Profile"