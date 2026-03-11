import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.cache import cache
from .models import StoryProject

class StoryProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]
        self.group_name = f"story_{self.project_id}"
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        rate_limit_key = f"ws_throttle_{self.user.id}"
        attempts = cache.get(rate_limit_key, 0)
        
        if attempts >= 20:
            await self.close(code=4429)
            return
            
        cache.set(rate_limit_key, attempts + 1, timeout=60)

        if not await self._is_project_owner():
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def progress(self, event):
        await self.send(json.dumps(event["event"]))

    @database_sync_to_async
    def _is_project_owner(self):
        return StoryProject.objects.filter(id=self.project_id, user=self.user).exists()