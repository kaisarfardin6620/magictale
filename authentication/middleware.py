from django.utils import translation
from rest_framework_simplejwt.authentication import JWTAuthentication
import logging

logger = logging.getLogger(__name__)

class UserLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = None
        try:
            if 'Authorization' in request.headers:
                auth = JWTAuthentication()
                auth_result = auth.authenticate(request)
                if auth_result:
                    user = auth_result[0]
        except Exception:
            pass

        current_user = user or getattr(request, 'user', None)

        if current_user and current_user.is_authenticated:
            try:
                user_lang = current_user.profile.language
                if user_lang:
                    translation.activate(user_lang)
                    request.LANGUAGE_CODE = user_lang
            except Exception as e:
                pass

        response = self.get_response(request)
        
        return response