from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token

@database_sync_to_async
def get_user_for_token(key: str):
    try:
        token = Token.objects.select_related("user").get(key=key)
        return token.user
    except Token.DoesNotExist:
        return AnonymousUser()

class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token_list = query.get("token", [])
        scope["user"] = AnonymousUser()
        if token_list:
            scope["user"] = await get_user_for_token(token_list[0])
        return await super().__call__(scope, receive, send)