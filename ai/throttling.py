from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone

class SubscriptionBasedThrottle(ScopedRateThrottle):
    def allow_request(self, request, view):
        user = request.user

        try:
            subscription = user.subscription
            is_active_or_grace = (
                subscription.status == 'active' or 
                (subscription.current_period_end and subscription.current_period_end > timezone.now())
            )
            
            if is_active_or_grace:
                self.scope = 'story_creation_paid'
            else:
                self.scope = 'story_creation_free'
        except (AttributeError, user.subscription.RelatedObjectDoesNotExist):
            self.scope = 'story_creation_free'

        return super().allow_request(request, view)