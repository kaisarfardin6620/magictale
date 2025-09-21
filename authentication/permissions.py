from rest_framework import permissions

class HasActiveSubscription(permissions.BasePermission):
    message = "An active subscription is required to perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        try:
            subscription = user.subscription
        except AttributeError:
            self.message = "You do not have a subscription."
            return False

        is_active = subscription.status in ['active', 'trialing']
        if not is_active:
            self.message = "Your subscription is not currently active."

        return is_active

class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user

class IsStoryMaster(permissions.BasePermission):
    message = "This feature requires a Story Master subscription."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        try:
            subscription = user.subscription
        except AttributeError:
            self.message = "You do not have a subscription."
            return False

        is_master_plan = subscription.plan == 'master'
        is_trialing = subscription.status == 'trialing'
        is_active_master = is_master_plan and subscription.status == 'active'

        return is_trialing or is_active_master