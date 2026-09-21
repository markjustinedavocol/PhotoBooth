from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import BoothSession, group_name_for

COUNTDOWN_SECONDS = 3
PAUSE_BETWEEN_SHOTS_MS = 1400


class BoothConsumer(AsyncJsonWebsocketConsumer):
    """One booth room. Relays presence, ready state and WebRTC signalling between
    the two partners, and starts the synced countdown."""

    group_name = None

    async def connect(self):
        self.user = self.scope["user"]
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        if not self.user.is_authenticated or not await self._is_member():
            await self.close(code=4403)
            return
        self.group_name = group_name_for(self.session_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if self.group_name:
            await self._relay({"type": "presence", "online": False})
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        kind = content.get("type")
        if kind == "hello":
            await self._relay(
                {"type": "hello", "ready": bool(content.get("ready")), "reply": bool(content.get("reply"))}
            )
        elif kind == "ready":
            await self._relay({"type": "ready", "ready": bool(content.get("ready"))})
        elif kind == "signal" and isinstance(content.get("data"), dict):
            await self._relay({"type": "signal", "data": content["data"]})
        elif kind == "start":
            await self._start()

    # ----- handlers for group messages

    async def relay(self, event):
        """Forward to everyone except the sender."""
        if event["sender"] != self.channel_name:
            await self.send_json({**event["payload"], "from": event["user"]})

    async def broadcast(self, event):
        """Send to everyone, sender included."""
        await self.send_json(event["payload"])

    # ----- helpers

    async def _relay(self, payload):
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "relay", "payload": payload, "sender": self.channel_name, "user": self.user.id},
        )

    async def _start(self):
        if not await self._claim_start():
            await self.send_json({"type": "error", "message": "This shoot has already started."})
            return
        shots = await self._shot_count()
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast",
                "payload": {
                    "type": "countdown",
                    "shots": shots,
                    "seconds": COUNTDOWN_SECONDS,
                    "pause": PAUSE_BETWEEN_SHOTS_MS,
                    "by": self.user.id,
                },
            },
        )

    @database_sync_to_async
    def _is_member(self):
        session = (
            BoothSession.objects.select_related("couple")
            .filter(pk=self.session_id, mode=BoothSession.Mode.DUO)
            .first()
        )
        return session is not None and session.couple.is_paired and session.can_join(self.user)

    @database_sync_to_async
    def _claim_start(self):
        return bool(
            BoothSession.objects.filter(
                pk=self.session_id, status=BoothSession.Status.WAITING
            ).update(status=BoothSession.Status.CAPTURING, captured_at=timezone.now())
        )

    @database_sync_to_async
    def _shot_count(self):
        return BoothSession.objects.values_list("shots", flat=True).get(pk=self.session_id)
