import json

from channels.generic.websocket import AsyncWebsocketConsumer


class RoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.slug = self.scope["url_route"]["kwargs"]["slug"]
        self.group = f"room_{self.slug}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        payload.setdefault("room", self.slug)
        await self.channel_layer.group_send(
            self.group,
            {"type": "room_event", "payload": payload},
        )

    async def room_event(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
