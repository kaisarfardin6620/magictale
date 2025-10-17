from rest_framework import permissions
from django.utils import timezone
from django.contrib.auth.models import User

class HasActiveSubscription(permissions.BasePermission):
    message = "An active subscription or trial is required to use this feature."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        try:
            subscription = user.subscription
        except (AttributeError, User.subscription.RelatedObjectDoesNotExist):
            self.message = "You do not have a subscription or trial."
            return False

        is_paid_active = (
            subscription.status == 'active' and 
            subscription.current_period_end is not None and 
            subscription.current_period_end > timezone.now()
        )
        is_in_trial = (
            subscription.status == 'trialing' and
            subscription.trial_end is not None and
            subscription.trial_end > timezone.now()
        )

        is_allowed = is_paid_active or is_in_trial
        
        if not is_allowed:
            self.message = "Your subscription or trial has ended. Please subscribe to continue."

        return is_allowed

class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'user'):
            return obj.user == request.user
        return False

class IsStoryMaster(permissions.BasePermission):
    message = "This feature requires a Story Master subscription."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        try:
            subscription = user.subscription
        except (AttributeError, User.subscription.RelatedObjectDoesNotExist):
            self.message = "You do not have a subscription or trial."
            return False
        
        return subscription.plan == 'master' and subscription.status == 'active'