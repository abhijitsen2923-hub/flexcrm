from enum import StrEnum


class UserRole(StrEnum):
    """User roles — three universal + six vertical-locked (Phase 8).

    The three legacy values (`admin`, `manager`, `sales`) are kept as enum
    members so the Phase 8 migration (`20260522_0010`) can read existing rows
    during the backfill remap. Application code rejects assigning them via the
    `ROLE_INDUSTRIES` map in `app/core/permissions.py`.
    """
    # Cross-vertical
    owner = "owner"
    support = "support"
    analyst = "analyst"
    # Education-only
    academic_admin = "academic_admin"
    counselor = "counselor"
    fee_admin = "fee_admin"
    # Travel-only
    ops_manager = "ops_manager"
    travel_agent = "travel_agent"
    visa_coordinator = "visa_coordinator"
    # Legacy — retained for migration backfill; not assignable post-0010.
    admin = "admin"
    manager = "manager"
    sales = "sales"


class UserStatus(StrEnum):
    active = "active"
    inactive = "inactive"
    invited = "invited"
    suspended = "suspended"


class CustomerStatus(StrEnum):
    active = "active"
    inactive = "inactive"
    prospect = "prospect"
    churned = "churned"


class CustomerLifecycleStage(StrEnum):
    """Post-sale lifecycle (spec §4.1).

    A customer transitions through these as the relationship matures.
    Distinct from `CustomerStatus` (kept for backward compatibility), which
    coarsely tracks active/inactive/prospect/churned.
    """
    onboarding = "onboarding"
    active = "active"
    at_risk = "at_risk"
    renewal_due = "renewal_due"
    renewed = "renewed"
    churned = "churned"


class InvoiceStatus(StrEnum):
    draft = "draft"
    issued = "issued"
    paid = "paid"
    refunded = "refunded"
    void = "void"


class PaymentStatus(StrEnum):
    pending = "pending"
    received = "received"
    refunded = "refunded"


class CommissionDirection(StrEnum):
    accrued = "accrued"
    payable = "payable"
    paid = "paid"
    reversed = "reversed"


class RenewalStatus(StrEnum):
    upcoming = "upcoming"
    renewed = "renewed"
    declined = "declined"


class ReferralStatus(StrEnum):
    pending = "pending"
    awarded = "awarded"
    dismissed = "dismissed"


class LeadIndustry(StrEnum):
    education = "education"
    travel = "travel"


class PipelineStageCategory(StrEnum):
    active = "active"
    closed_won = "closed_won"
    closed_lost = "closed_lost"


class DealStage(StrEnum):
    discovery = "discovery"
    proposal = "proposal"
    negotiation = "negotiation"
    closed_won = "closed_won"
    closed_lost = "closed_lost"


class DealStatus(StrEnum):
    open = "open"
    won = "won"
    lost = "lost"
    on_hold = "on_hold"


class TaskPriority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class TaskStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ActivityType(StrEnum):
    note = "note"
    call = "call"
    email = "email"
    meeting = "meeting"
    task = "task"
    status_change = "status_change"


class NotificationStatus(StrEnum):
    unread = "unread"
    read = "read"
