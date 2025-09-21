from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from .models import UserProfile

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        
        if not hasattr(user, 'profile'):
            UserProfile.objects.create(user=user)
            
        return user