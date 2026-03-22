import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .models import (
    ChatConversation,
    ChatConversationMessage,
    ChatConversationParticipant,
    ChatMessageReadReceipt,
    Membership,
    Notification,
    create_notification,
)


class ConversationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.family_id = int(self.scope["url_route"]["kwargs"]["family_id"])
        self.conversation_id = int(self.scope["url_route"]["kwargs"]["conversation_id"])
        self.room_group_name = f"conversation_{self.conversation_id}"
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        allowed = await self._ensure_membership()
        if not allowed:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        for update in await self._mark_read_and_collect_updates():
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "receipt_update",
                    "message_id": update["message_id"],
                    "receipt_text": update["receipt_text"],
                },
            )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        payload = json.loads(text_data)
        action = payload.get("action")

        if action == "send_message":
            content = (payload.get("content") or "").strip()
            if not content:
                return
            message = await self._create_message(content)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": message,
                },
            )
        elif action == "mark_read":
            for update in await self._mark_read_and_collect_updates():
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "receipt_update",
                        "message_id": update["message_id"],
                        "receipt_text": update["receipt_text"],
                    },
                )

    async def chat_message(self, event):
        message = dict(event["message"])
        message["is_own"] = message["author_id"] == self.user.id
        if message["is_own"]:
            message["author_label"] = "You"
        await self.send(text_data=json.dumps({
            "type": "message",
            "message": message,
        }))

    async def receipt_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "receipt",
            "message_id": event["message_id"],
            "receipt_text": event["receipt_text"],
        }))

    @database_sync_to_async
    def _ensure_membership(self):
        membership = Membership.objects.filter(family_id=self.family_id, user=self.user).first()
        if not membership:
            return False

        conversation = ChatConversation.objects.filter(
            id=self.conversation_id,
            family_id=self.family_id,
        ).first()
        if not conversation:
            return False

        if conversation.conversation_type != ChatConversation.ConversationType.DIRECT:
            ChatConversationParticipant.objects.get_or_create(
                conversation=conversation,
                user=self.user,
            )
            return True

        return ChatConversationParticipant.objects.filter(
            conversation=conversation,
            user=self.user,
        ).exists()

    @database_sync_to_async
    def _create_message(self, content):
        conversation = ChatConversation.objects.get(id=self.conversation_id, family_id=self.family_id)
        message = ChatConversationMessage.objects.create(
            conversation=conversation,
            author=self.user,
            content=content,
        )
        conversation.save(update_fields=["updated_at"])

        other_participants = ChatConversationParticipant.objects.filter(
            conversation=conversation,
        ).exclude(user=self.user).select_related("user")
        for participant in other_participants:
            create_notification(
                recipient=participant.user,
                notification_type=Notification.NotificationType.CHAT,
                title=f"New message in {conversation.title or conversation.get_conversation_type_display()}",
                message=f"{self.user.email}: {content[:50]}...",
                link=f"/families/{self.family_id}/messages/conversations/{conversation.id}/",
                family=conversation.family,
            )

        return {
            "id": message.id,
            "author_id": self.user.id,
            "author_label": self.user.profile.get_display_name() if hasattr(self.user, "profile") else self.user.email.split("@")[0],
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "is_own": False,
            "receipt_text": "",
        }

    @database_sync_to_async
    def _mark_read_and_collect_updates(self):
        conversation = ChatConversation.objects.get(id=self.conversation_id, family_id=self.family_id)
        now = timezone.now()
        updates = []

        unread_messages = ChatConversationMessage.objects.filter(
            conversation=conversation,
            is_deleted=False,
        ).exclude(author=self.user)

        for message in unread_messages:
            ChatMessageReadReceipt.objects.update_or_create(
                message=message,
                user=self.user,
                defaults={"read_at": now},
            )
            receipts = list(
                message.read_receipts.select_related("user", "user__profile").exclude(user=message.author)
            )
            labels = [
                receipt.user.profile.get_display_name() if hasattr(receipt.user, "profile") else receipt.user.email.split("@")[0]
                for receipt in receipts
            ]
            updates.append({
                "message_id": message.id,
                "receipt_text": f"Seen by {', '.join(labels)}" if labels else "",
            })

        ChatConversationParticipant.objects.filter(
            conversation=conversation,
            user=self.user,
        ).update(last_read_at=now)
        return updates
