from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.tenancy import OrgScopedMixin
from app.database.base import Base
from app.database.enums import ReferralStatus
from app.models.base import UUIDPrimaryKeyMixin


class Referral(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    __tablename__ = "referrals"
    __table_args__ = (
        Index("ix_referrals_referring_customer", "referring_customer_id"),
        Index("ix_referrals_referred_lead", "referred_lead_id"),
    )

    referring_customer_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    referred_lead_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    awarded_credit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus, name="referral_status_enum"),
        nullable=False,
        default=ReferralStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    referring_customer = relationship(
        "Customer",
        back_populates="referrals",
        foreign_keys=[referring_customer_id],
    )
    referred_lead = relationship("Lead", foreign_keys=[referred_lead_id])
