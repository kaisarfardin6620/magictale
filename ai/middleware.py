from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
import jwt

@database_sync_to_async
def get_user_from_jwt(token_key: str):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        UntypedToken(token_key)
        decoded_data = jwt_decode(token_key, settings.SECRET_KEY, algorithms=[settings.SIMPLE_JWT['ALGORITHM']])
        user_id = decoded_data.get('user_id')
        return User.objects.get(id=user_id)
    except (InvalidToken, TokenError, jwt.ExpiredSignatureError, jwt.InvalidTokenError, User.DoesNotExist, Exception):
        return AnonymousUser()

class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token_list = query.get("token", [])
        
        if not token_list:
            scope["user"] = AnonymousUser()
        else:
            scope["user"] = await get_user_from_jwt(token_list[0])
            
        return await super().__call__(scope, receive, send)