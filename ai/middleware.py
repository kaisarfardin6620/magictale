# ai/middleware.py

from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser, User
from django.conf import settings
import jwt

@database_sync_to_async
def get_user_from_jwt(token_key: str):
    """
    Decodes a JWT token and fetches the corresponding user.
    """
    try:
        # Decode the token using the secret key from your settings
        decoded_data = jwt.decode(token_key, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = decoded_data['user_id']
        return User.objects.get(id=user_id)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, User.DoesNotExist):
        # Handle cases where the token is invalid or the user doesn't exist
        return AnonymousUser()

class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Parse the token from the query string (e.g., ws://.../?token=ey...)
        query = parse_qs(scope.get("query_string", b"").decode())
        token_list = query.get("token", [])
        
        if not token_list:
            scope["user"] = AnonymousUser()
        else:
            # Get the user associated with the token
            scope["user"] = await get_user_from_jwt(token_list[0])
            
        return await super().__call__(scope, receive, send)