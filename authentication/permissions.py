# authentication/permissions.py

from rest_framework import permissions

class HasActiveSubscription(permissions.BasePermission):
    """
    Custom permission to only allow users with an active or trialing subscription.
    This now correctly checks the user's related Subscription object, which is the
    single source of truth for subscription status.
    """
    message = "An active subscription is required to perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        try:
            # This is the standard Django way to access a one-to-one related object.
            # It assumes your Subscription model has a OneToOneField to the User model
            # with a related_name of 'subscription'.
            subscription = user.subscription
        except AttributeError: 
            # This will catch the error if the 'subscription' relation doesn't exist
            # (e.g., the user has never subscribed or the related_name is different).
            self.message = "You do not have a subscription."
            return False

        # The core logic: allow access only if the status is valid.
        is_active = subscription.status in ['active', 'trialing']
        if not is_active:
            self.message = "Your subscription is not currently active."
        
        return is_active

class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to view or edit it.
    """
    def has_object_permission(self, request, view, obj):
        # This check works for any model that has a 'user' field.
        return obj.user == request.user        