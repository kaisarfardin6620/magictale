# ai/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import StoryProject

class StoryProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]
        self.group_name = f"story_{self.project_id}"
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # CRITICAL FIX: Check if the connected user owns the project
        if not await self._is_project_owner():
            await self.close(code=4003) # 4003 = Forbidden
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
        """
        Runs a DB query to check if the user is the owner of the project.
        """
        return StoryProject.objects.filter(id=self.project_id, user=self.user).exists()