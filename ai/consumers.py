import json
from channels.generic.websocket import AsyncWebsocketConsumer

class StoryProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]
        self.group_name = f"story_{self.project_id}"

        if not self.scope.get("user") or not self.scope["user"].is_authenticated:
            await self.close(code=4001)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def progress(self, event):
        await self.send(json.dumps(event["event"]))