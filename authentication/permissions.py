from rest_framework import permissions

class HasActiveSubscription(permissions.BasePermission):
    """
    Custom permission to only allow users with an active or trialing subscription.
    """
    message = "An active subscription is required to perform this action."

    def has_permission(self, request, view):
        # Ensure the user is authenticated before checking for a subscription
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            # Check for a 'subscription' attribute on the user object
            subscription = request.user.subscription
            
            # Allow access if the status is 'active' or 'trialing'
            if subscription.status in ['active', 'trialing']:
                return True

        except AttributeError:
            # This handles the case where user.subscription doesn't exist
            self.message = "You do not have a subscription."
            return False
        
        # If the subscription exists but status is not valid (e.g., 'canceled')
        self.message = "Your subscription is not currently active."
        return False