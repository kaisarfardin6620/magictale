from rest_framework.throttling import ScopedRateThrottle

class SubscriptionBasedThrottle(ScopedRateThrottle):
    def allow_request(self, request, view):
        user = request.user

        try:
            subscription = user.subscription
            if subscription.status == 'active':
                self.scope = 'story_creation_paid'
            else:
                self.scope = 'story_creation_free'
        except (AttributeError, user.subscription.RelatedObjectDoesNotExist):
            self.scope = 'story_creation_free'

        return super().allow_request(request, view)