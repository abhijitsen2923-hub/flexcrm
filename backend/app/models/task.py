from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.database.enums import TaskPriority, TaskStatus
from app.models.user import User  # direct ref to avoid cross-registry string lookup
from app.models.base import TenantAuditMixin, TenantSoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Task(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_assigned_due_date", "assigned_to_id", "due_date"),
        Index("ix_tasks_status_priority", "status", "priority"),
        {"schema": "tenant"},
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority_enum"),
        nullable=False,
        default=TaskPriority.medium,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status_enum"),
        nullable=False,
        default=TaskStatus.pending,
    )

    # Cross-schema relationship to public.users. The FK string "public.users.id"
    # registers a stub table in TenantBase.metadata distinct from the real User
    # mapper in Base.metadata, so SQLAlchemy can't infer the join — specify it
    # explicitly (same pattern as Lead.assigned_to / StageTransition.performed_by).
    # viewonly: the assignee is written via assigned_to_id. Without this
    # relationship the repository's selectinload(Task.assigned_to) raises
    # AttributeError and every list/get/create/update of a task 500s.
    assigned_to = relationship(
        User,
        primaryjoin=lambda: Task.assigned_to_id == User.id,
        foreign_keys=lambda: [Task.assigned_to_id],
        viewonly=True,
    )

