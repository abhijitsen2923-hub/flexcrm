from uuid import UUID

from fastapi import BackgroundTasks

from app.core.exceptions import NotFoundError
from app.core.tenancy import current_org
from app.repositories.tasks import TaskRepository
from app.repositories.users import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.task import TaskCreate, TaskFilterParams, TaskUpdate
from app.services.base import ServiceBase
from app.services.email import EmailService
from app.services.notifications import NotificationService
from app.services.realtime import realtime_manager
from app.utils.query import validate_sort_field


class TaskService(ServiceBase):
    allowed_sort_fields = {"created_at", "updated_at", "title", "due_date", "priority", "status"}

    def __init__(self, session):
        super().__init__(session)
        self.repository = TaskRepository(session)
        self.user_repository = UserRepository(session)
        self.notification_service = NotificationService(session)
        self.email_service = EmailService()

    async def list_tasks(self, pagination: PaginationParams, filters: TaskFilterParams):
        sort_by = validate_sort_field(filters.sort_by, self.allowed_sort_fields)
        return await self.repository.list(
            pagination=pagination,
            filters={
                "assigned_to_id": filters.assigned_to_id,
                "priority": filters.priority,
                "status": filters.status,
            },
            search=filters.search,
            search_fields=("title", "description"),
            sort_by=sort_by,
            sort_order=filters.sort_order,
            options=self.repository.default_options,
        )

    async def get_task(self, task_id: UUID):
        task = await self.repository.get(task_id, options=self.repository.default_options)
        if task is None:
            raise NotFoundError("Task not found.")
        return task

    async def create_task(
        self,
        payload: TaskCreate,
        *,
        actor_id: UUID,
        background_tasks: BackgroundTasks | None = None,
    ):
        await self._ensure_assignee(payload.assigned_to_id)
        task = await self.repository.create(
            {
                **payload.model_dump(),
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        if payload.assigned_to_id:
            await self._notify_assignee(payload.assigned_to_id, f"Task assigned: {payload.title}", payload.title, background_tasks)
        await self.commit()
        await self.invalidate_reporting_cache()
        task = await self.get_task(task.id)
        await realtime_manager.broadcast({"event": "task.created", "payload": {"id": str(task.id), "title": task.title}})
        return task

    async def update_task(
        self,
        task_id: UUID,
        payload: TaskUpdate,
        *,
        actor_id: UUID,
        background_tasks: BackgroundTasks | None = None,
    ):
        task = await self.get_task(task_id)
        update_data = payload.model_dump(exclude_unset=True)
        if "assigned_to_id" in update_data:
            await self._ensure_assignee(update_data["assigned_to_id"])
        update_data["updated_by_id"] = actor_id
        task = await self.repository.update(task, update_data)
        if update_data.get("assigned_to_id"):
            await self._notify_assignee(update_data["assigned_to_id"], f"Task assigned: {task.title}", task.title, background_tasks)
        await self.commit()
        await self.invalidate_reporting_cache()
        task = await self.get_task(task.id)
        await realtime_manager.broadcast({"event": "task.updated", "payload": {"id": str(task.id), "title": task.title}})
        return task

    async def delete_task(self, task_id: UUID, *, actor_id: UUID):
        task = await self.get_task(task_id)
        await self.repository.soft_delete(task, actor_id)
        await self.commit()
        await self.invalidate_reporting_cache()
        await realtime_manager.broadcast({"event": "task.deleted", "payload": {"id": str(task.id)}})

    async def _ensure_assignee(self, assigned_to_id: UUID | None) -> None:
        if assigned_to_id is None:
            return
        # Org-scoped: prevent assigning a task to a user in another tenant (IDOR).
        user = await self.user_repository.get_in_org(assigned_to_id, current_org(self.session))
        if user is None:
            raise NotFoundError("Assigned user not found.")

    async def _notify_assignee(
        self,
        assignee_id: UUID,
        message: str,
        resource_title: str,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        assignee = await self.user_repository.get_in_org(assignee_id, current_org(self.session))
        if assignee is None:
            return
        await self.notification_service.create_notification(user_id=assignee_id, message=message)
        if background_tasks:
            background_tasks.add_task(
                self.email_service.send_assignment_email,
                assignee.email,
                assignee.first_name,
                resource_title,
            )
