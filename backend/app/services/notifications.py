from uuid import UUID

from app.database.enums import NotificationStatus
from app.repositories.notifications import NotificationRepository
from app.services.realtime import realtime_manager


class NotificationService:
    def __init__(self, session):
        self.repository = NotificationRepository(session)

    async def create_notification(self, *, user_id: UUID, message: str):
        notification = await self.repository.create(
            {
                "user_id": user_id,
                "message": message,
                "read_status": NotificationStatus.unread,
            }
        )
        await realtime_manager.broadcast_to_user(
            user_id,
            {
                "event": "notification.created",
                "payload": {
                    "id": str(notification.id),
                    "message": notification.message,
                    "read_status": notification.read_status,
                    "created_at": notification.created_at.isoformat(),
                },
            },
        )
        return notification
