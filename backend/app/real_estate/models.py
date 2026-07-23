"""Real estate domain models — per-tenant schema."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import TenantBase
from app.database.enums import BookingStatus, SiteVisitFeedback, UnitStatus
from app.models.base import TenantAuditMixin, TenantSoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Project(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "projects"
    __table_args__ = ({"schema": "tenant"},)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    builder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    rera_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- Project detail (Phase B) — declared specs from the brochure / RERA.
    # Distinct from the derived tower/unit counts; these are the announced totals.
    pin_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_towers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flats_per_floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_garages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Garage / parking types offered — subset of MLP/CP/IP/OP (validated app-side).
    garage_options: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- Default box-price components (Phase B) — seed the booking PriceCalculator
    # so a new booking pre-fills from the project instead of every field at ₹0.
    rate_a: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # ₹/sqft — residential
    rate_b: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # ₹/sqft — shop / commercial
    rate_c: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # ₹/sqft — godown / other
    parking_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    legal_fees: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    overhead_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    other_charges: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    sinking_fund: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    amenities_charges: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    towers: Mapped[list["Tower"]] = relationship(
        "Tower", back_populates="project", cascade="all, delete-orphan"
    )
    media: Mapped[list["ProjectMedia"]] = relationship(
        "ProjectMedia", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMedia(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "project_media"
    __table_args__ = ({"schema": "tenant"},)

    project_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # brochure / floor_plan / image / video / virtual_tour — validated app-side.
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Object storage key (not a public URL) — served via presigned GET URLs.
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="media")

    # Convenience accessors so the read schema (ProjectMediaRead) maps directly
    # via from_attributes: `type` aliases the column, `url` signs the key. Guarded
    # so a project GET never 503s when storage is unconfigured (media list is then
    # empty anyway, so this is only hit when a key genuinely exists).
    @property
    def type(self) -> str:
        return self.media_type

    @property
    def url(self) -> str:
        from app.core import storage

        return storage.presigned_get_url(self.file_path) if storage.is_configured() else ""


class Tower(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantSoftDeleteMixin):
    __tablename__ = "towers"
    __table_args__ = ({"schema": "tenant"},)

    project_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    total_floors: Mapped[int] = mapped_column(Integer, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="towers")
    units: Mapped[list["Unit"]] = relationship(
        "Unit", back_populates="tower", cascade="all, delete-orphan"
    )


class Unit(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantSoftDeleteMixin):
    __tablename__ = "units"
    __table_args__ = (
        Index("ix_units_project_status", "project_id", "status"),
        Index("ix_units_tower_floor", "tower_id", "floor"),
        {"schema": "tenant"},
    )

    project_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tower_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("towers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_number: Mapped[str] = mapped_column(String(20), nullable=False)
    # residential / parking / shop / godown — validated app-side via UnitType.
    unit_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="residential")
    area: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    area_unit: Mapped[str] = mapped_column(String(20), nullable=False, default="sqft")
    facing: Mapped[str | None] = mapped_column(String(50), nullable=True)
    view: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[UnitStatus] = mapped_column(
        Enum(UnitStatus, name="unit_status_enum"),
        nullable=False,
        default=UnitStatus.available,
    )

    tower: Mapped["Tower"] = relationship("Tower", back_populates="units")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="unit")

    # Convenience names for read schemas (BookingUnitInfo). Only accessed when the
    # tower + project are eager-loaded, so they never trigger a lazy load.
    @property
    def tower_name(self) -> str | None:
        return self.tower.name if self.tower else None

    @property
    def project_name(self) -> str | None:
        return self.tower.project.name if self.tower and self.tower.project else None


class SiteVisit(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin):
    __tablename__ = "site_visits"
    __table_args__ = (
        Index("ix_site_visits_project_scheduled", "project_id", "scheduled_at"),
        {"schema": "tenant"},
    )

    lead_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    assigned_to_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feedback: Mapped[SiteVisitFeedback | None] = mapped_column(
        Enum(SiteVisitFeedback, name="site_visit_feedback_enum"), nullable=True
    )
    attended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # scheduled / completed / cancelled — validated app-side.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="scheduled")

    project: Mapped["Project"] = relationship("Project")
    # Read-only link to the lead for display (lead name/number on the calendar).
    lead = relationship("Lead", foreign_keys=[lead_id], viewonly=True)


class Booking(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin, TenantAuditMixin, TenantSoftDeleteMixin):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_unit", "unit_id"),
        Index("ix_bookings_customer", "customer_id"),
        {"schema": "tenant"},
    )

    unit_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status_enum"),
        nullable=False,
        default=BookingStatus.draft,
    )
    pricing_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Post-registration handover checklist — a list of booleans aligned with the
    # UI's checklist items. Persisted so the Possession Tracker survives refresh.
    possession_checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Optional note captured when a booking is cancelled.
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Registration (legal milestone) record — captured when marking Registered.
    registration_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sub_registrar_office: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Token / booking amount (Phase C) — the initial money that confirms the booking
    # (the "Booked / Token" stage). Kept first-class on the booking so the lead is the
    # source of truth for it without digging through payment receipts.
    token_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    token_received_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    token_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # upi/neft/cheque/cash/card/other
    token_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    unit: Mapped["Unit"] = relationship("Unit", back_populates="bookings")
    # Read-only link to the customer for display (name on lists/trackers/docs).
    customer = relationship("Customer", foreign_keys=[customer_id], viewonly=True)
    kyc_documents: Mapped[list["BookingKycDoc"]] = relationship(
        "BookingKycDoc", back_populates="booking", cascade="all, delete-orphan"
    )
    payment_schedules: Mapped[list["PaymentSchedule"]] = relationship(
        "PaymentSchedule", back_populates="booking", cascade="all, delete-orphan"
    )
    payment_receipts: Mapped[list["PaymentReceipt"]] = relationship(
        "PaymentReceipt",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="PaymentReceipt.paid_on",
    )
    refunds: Mapped[list["BookingRefund"]] = relationship(
        "BookingRefund",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingRefund.refunded_on",
    )


class BookingKycDoc(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "booking_kyc_docs"
    __table_args__ = ({"schema": "tenant"},)

    booking_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    booking: Mapped["Booking"] = relationship("Booking", back_populates="kyc_documents")


class PaymentSchedule(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payment_schedules"
    __table_args__ = (
        Index("ix_payment_schedules_booking_due_date", "booking_id", "due_date"),
        {"schema": "tenant"},
    )

    booking_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installment_name: Mapped[str] = mapped_column(String(120), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    demand_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    outstanding: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    is_overdue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    booking: Mapped["Booking"] = relationship("Booking", back_populates="payment_schedules")


class PaymentReceipt(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single collection transaction posted against a booking / installment."""
    __tablename__ = "payment_receipts"
    __table_args__ = (
        Index("ix_payment_receipts_booking", "booking_id"),
        {"schema": "tenant"},
    )

    booking_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Which installment this payment is applied to (nullable → ad-hoc payment).
    schedule_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("payment_schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # upi/neft/cheque/cash/card/other
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking: Mapped["Booking"] = relationship("Booking", back_populates="payment_receipts")


class BookingRefund(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """A refund issued when a paid booking is cancelled.

    `gross_paid` snapshots the total collected at refund time; `deduction_amount`
    is the forfeiture / cancellation charge withheld by the builder; `refund_amount`
    is the net paid back to the buyer (gross_paid − deduction). Recording a refund
    is what cancels an otherwise-blocked paid booking (see the cancel guard)."""
    __tablename__ = "booking_refunds"
    __table_args__ = (
        Index("ix_booking_refunds_booking", "booking_id"),
        {"schema": "tenant"},
    )

    booking_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gross_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    deduction_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # upi/neft/cheque/cash/card/other
    refunded_on: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking: Mapped["Booking"] = relationship("Booking", back_populates="refunds")
