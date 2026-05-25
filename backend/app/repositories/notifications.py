from sqlalchemy import select

from app.database.enums import NotificationStatus
from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session):
        super().__init__(session, Notification)

    async def unread_for_user(self, user_id):
        query = select(Notification).where(
            Notification.user_id == user_id,
            Notification.read_status == NotificationStatus.unread,
            Notification.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
