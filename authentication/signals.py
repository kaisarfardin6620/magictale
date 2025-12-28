from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile
from subscription.models import Subscription
from django.utils import timezone
from datetime import timedelta

@receiver(post_save, sender=User)
def create_user_relationships(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
        
        if not hasattr(instance, 'subscription'):
            now = timezone.now()
            Subscription.objects.create(
                user=instance,
                plan='trial',
                status='trialing',
                trial_start=now,
                trial_end=now + timedelta(days=14)
            )

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()