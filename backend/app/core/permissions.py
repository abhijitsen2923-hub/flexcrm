"""Permission catalog, role defaults, and vertical-role validation.

The five originals (admin/manager/sales/support/analyst) collapsed into nine:
three universal roles (`owner`, `support`, `analyst`) and six vertical-locked
roles split across education and travel. The map `ROLE_INDUSTRIES` says which
verticals each role is valid for — `UserService` rejects cross-vertical
assignment (e.g. a `visa_coordinator` in an education org).

Permissions are fine-grained codes. Each role ships with a default set in
`ROLE_PERMISSION_DEFAULTS`; admins can layer per-user overrides via the
`user_permission_grants` table. Final permissions for a user are
`defaults ∪ explicit_grants`, then alias-expanded (e.g. granting `LEAD_MANAGE`
implies `LEAD_VIEW`).

The hard-coded dict approach: defaults live in code (this file) and changing
them requires editing + redeploying. Runtime flexibility comes from grants.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from app.database.enums import LeadIndustry, UserRole


class PermissionCode(StrEnum):
    """All fine-grained permissions in the system.

    Convention: `DOMAIN_VERB`. View permissions are the lowest unit; manage
    permissions imply view via `PERMISSION_ALIASES` so admins can grant the
    coarse code and pick up the fine codes for free.
    """
    DASHBOARD_VIEW = "DASHBOARD_VIEW"

    LEAD_VIEW = "LEAD_VIEW"
    LEAD_MANAGE = "LEAD_MANAGE"
    LEAD_IMPORT = "LEAD_IMPORT"
    LEAD_DOCS_MANAGE = "LEAD_DOCS_MANAGE"

    CUSTOMER_VIEW = "CUSTOMER_VIEW"
    CUSTOMER_MANAGE = "CUSTOMER_MANAGE"

    DEAL_VIEW = "DEAL_VIEW"
    DEAL_MANAGE = "DEAL_MANAGE"

    TASK_VIEW = "TASK_VIEW"
    TASK_MANAGE = "TASK_MANAGE"

    ACTIVITY_VIEW = "ACTIVITY_VIEW"
    ACTIVITY_MANAGE = "ACTIVITY_MANAGE"

    FINANCE_VIEW = "FINANCE_VIEW"
    FINANCE_RECORD_PAYMENT = "FINANCE_RECORD_PAYMENT"
    FINANCE_REFUND = "FINANCE_REFUND"

    HR_VIEW = "HR_VIEW"
    HR_MANAGE = "HR_MANAGE"

    USER_VIEW = "USER_VIEW"
    USER_MANAGE = "USER_MANAGE"

    ORG_MANAGE = "ORG_MANAGE"

    ANALYTICS_VIEW = "ANALYTICS_VIEW"
    REPORTS_VIEW = "REPORTS_VIEW"

    EXPORT_DATA = "EXPORT_DATA"


# Which verticals each role can be assigned in. `None` in the frozenset means
# the role is vertical-agnostic — it works in either an Education or a Travel
# org. Used by `UserService.create_user` / `UserService.update_user`.
ROLE_INDUSTRIES: dict[UserRole, frozenset[LeadIndustry | None]] = {
    # Cross-vertical
    UserRole.owner: frozenset({None}),
    UserRole.support: frozenset({None}),
    UserRole.analyst: frozenset({None}),
    # Education
    UserRole.academic_admin: frozenset({LeadIndustry.education}),
    UserRole.counselor: frozenset({LeadIndustry.education}),
    UserRole.fee_admin: frozenset({LeadIndustry.education}),
    # Travel
    UserRole.ops_manager: frozenset({LeadIndustry.travel}),
    UserRole.travel_agent: frozenset({LeadIndustry.travel}),
    UserRole.visa_coordinator: frozenset({LeadIndustry.travel}),
    # Real estate
    UserRole.sales_manager: frozenset({LeadIndustry.real_estate}),
    UserRole.sales_executive: frozenset({LeadIndustry.real_estate}),
    UserRole.telecaller: frozenset({LeadIndustry.real_estate}),
    UserRole.accounts: frozenset({LeadIndustry.real_estate}),
    UserRole.crm_team: frozenset({LeadIndustry.real_estate}),
    UserRole.broker: frozenset({LeadIndustry.real_estate}),
    UserRole.customer: frozenset({LeadIndustry.real_estate}),
}


# Legacy roles still defined on the enum (so the 0010 backfill can read them)
# but no longer assignable from the application. Trying to set a user to any
# of these via the API raises ValidationError.
LEGACY_ROLES: frozenset[UserRole] = frozenset({UserRole.admin, UserRole.manager, UserRole.sales})


def role_is_valid_for_industry(role: UserRole, industry: LeadIndustry | None) -> bool:
    """True if `role` may be assigned to a user in an org of the given industry.

    Legacy roles always return False — they exist only for the backfill.
    """
    if role in LEGACY_ROLES:
        return False
    allowed = ROLE_INDUSTRIES.get(role)
    if allowed is None:
        return False
    # Cross-vertical roles have `None` in their allowed set.
    if None in allowed:
        return True
    return industry is not None and industry in allowed


def roles_for_industry(industry: LeadIndustry) -> list[UserRole]:
    """Return the roles assignable to users in an org of the given industry.

    Excludes legacy roles. Order is: cross-vertical first, then vertical-specific.
    Used by the admin user-create modal to populate the role dropdown.
    """
    return [
        role for role in ROLE_INDUSTRIES
        if role_is_valid_for_industry(role, industry)
    ]


# Default permissions per role. Owners get everything; vertical admins get
# everything except user/org management; sales-flavoured roles get the
# operational surface; specialist roles get targeted slices.
_ALL_PERMISSIONS: tuple[PermissionCode, ...] = tuple(PermissionCode)

_VIEW_ONLY: tuple[PermissionCode, ...] = tuple(
    code for code in PermissionCode if code.value.endswith("_VIEW")
)

ROLE_PERMISSION_DEFAULTS: dict[UserRole, tuple[PermissionCode, ...]] = {
    UserRole.owner: _ALL_PERMISSIONS,

    UserRole.academic_admin: tuple(
        code for code in _ALL_PERMISSIONS
        if code not in {PermissionCode.USER_MANAGE, PermissionCode.ORG_MANAGE}
    ),
    UserRole.ops_manager: tuple(
        code for code in _ALL_PERMISSIONS
        if code not in {PermissionCode.USER_MANAGE, PermissionCode.ORG_MANAGE}
    ),

    UserRole.counselor: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW, PermissionCode.LEAD_MANAGE, PermissionCode.LEAD_IMPORT,
        PermissionCode.CUSTOMER_VIEW, PermissionCode.CUSTOMER_MANAGE,
        PermissionCode.DEAL_VIEW, PermissionCode.DEAL_MANAGE,
        PermissionCode.TASK_VIEW, PermissionCode.TASK_MANAGE,
        PermissionCode.ACTIVITY_VIEW, PermissionCode.ACTIVITY_MANAGE,
        PermissionCode.FINANCE_VIEW, PermissionCode.FINANCE_RECORD_PAYMENT,
        PermissionCode.EXPORT_DATA,
    ),
    UserRole.travel_agent: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW, PermissionCode.LEAD_MANAGE, PermissionCode.LEAD_IMPORT,
        PermissionCode.CUSTOMER_VIEW, PermissionCode.CUSTOMER_MANAGE,
        PermissionCode.DEAL_VIEW, PermissionCode.DEAL_MANAGE,
        PermissionCode.TASK_VIEW, PermissionCode.TASK_MANAGE,
        PermissionCode.ACTIVITY_VIEW, PermissionCode.ACTIVITY_MANAGE,
        PermissionCode.FINANCE_VIEW, PermissionCode.FINANCE_RECORD_PAYMENT,
        PermissionCode.EXPORT_DATA,
    ),

    UserRole.fee_admin: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.CUSTOMER_VIEW,
        PermissionCode.FINANCE_VIEW, PermissionCode.FINANCE_RECORD_PAYMENT, PermissionCode.FINANCE_REFUND,
        PermissionCode.REPORTS_VIEW,
        PermissionCode.EXPORT_DATA,
    ),

    UserRole.visa_coordinator: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW, PermissionCode.LEAD_DOCS_MANAGE,
        PermissionCode.CUSTOMER_VIEW,
        PermissionCode.TASK_VIEW, PermissionCode.TASK_MANAGE,
        PermissionCode.ACTIVITY_VIEW, PermissionCode.ACTIVITY_MANAGE,
    ),

    UserRole.support: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW,
        PermissionCode.CUSTOMER_VIEW,
        PermissionCode.TASK_VIEW, PermissionCode.TASK_MANAGE,
        PermissionCode.ACTIVITY_VIEW, PermissionCode.ACTIVITY_MANAGE,
    ),

    UserRole.analyst: _VIEW_ONLY + (
        PermissionCode.ANALYTICS_VIEW,
        PermissionCode.REPORTS_VIEW,
        PermissionCode.EXPORT_DATA,
    ),

    # Real estate roles
    UserRole.sales_manager: tuple(
        code for code in _ALL_PERMISSIONS
        if code not in {PermissionCode.USER_MANAGE, PermissionCode.ORG_MANAGE}
    ),
    UserRole.sales_executive: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW, PermissionCode.LEAD_MANAGE, PermissionCode.LEAD_IMPORT,
        PermissionCode.CUSTOMER_VIEW, PermissionCode.CUSTOMER_MANAGE,
        PermissionCode.TASK_VIEW, PermissionCode.TASK_MANAGE,
        PermissionCode.ACTIVITY_VIEW, PermissionCode.ACTIVITY_MANAGE,
        PermissionCode.FINANCE_VIEW,
    ),
    UserRole.telecaller: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW, PermissionCode.LEAD_MANAGE,
        PermissionCode.CUSTOMER_VIEW,
        PermissionCode.TASK_VIEW, PermissionCode.TASK_MANAGE,
        PermissionCode.ACTIVITY_VIEW, PermissionCode.ACTIVITY_MANAGE,
    ),
    UserRole.accounts: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.CUSTOMER_VIEW,
        PermissionCode.FINANCE_VIEW, PermissionCode.FINANCE_RECORD_PAYMENT, PermissionCode.FINANCE_REFUND,
        PermissionCode.REPORTS_VIEW,
        PermissionCode.EXPORT_DATA,
    ),
    UserRole.crm_team: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW, PermissionCode.LEAD_MANAGE,
        PermissionCode.CUSTOMER_VIEW, PermissionCode.CUSTOMER_MANAGE,
        PermissionCode.TASK_VIEW, PermissionCode.TASK_MANAGE,
        PermissionCode.ACTIVITY_VIEW, PermissionCode.ACTIVITY_MANAGE,
    ),
    UserRole.broker: (
        PermissionCode.DASHBOARD_VIEW,
        PermissionCode.LEAD_VIEW, PermissionCode.LEAD_MANAGE,
        PermissionCode.CUSTOMER_VIEW,
    ),
    UserRole.customer: (
        PermissionCode.DASHBOARD_VIEW,
    ),
    # Legacy — defaults to empty so a legacy row only retains permissions the
    # backfill should have already remapped away from.
    UserRole.admin: _ALL_PERMISSIONS,  # treat unmigrated rows as owners
    UserRole.manager: (),
    UserRole.sales: (),
}


# Coarse code → fine codes it implies. Granting the coarse one unlocks all
# implied ones too. Used by `effective_permissions_for_user` after combining
# defaults + explicit grants.
PERMISSION_ALIASES: dict[PermissionCode, tuple[PermissionCode, ...]] = {
    PermissionCode.LEAD_MANAGE: (PermissionCode.LEAD_VIEW,),
    PermissionCode.LEAD_IMPORT: (PermissionCode.LEAD_VIEW,),
    PermissionCode.LEAD_DOCS_MANAGE: (PermissionCode.LEAD_VIEW,),
    PermissionCode.CUSTOMER_MANAGE: (PermissionCode.CUSTOMER_VIEW,),
    PermissionCode.DEAL_MANAGE: (PermissionCode.DEAL_VIEW,),
    PermissionCode.TASK_MANAGE: (PermissionCode.TASK_VIEW,),
    PermissionCode.ACTIVITY_MANAGE: (PermissionCode.ACTIVITY_VIEW,),
    PermissionCode.FINANCE_RECORD_PAYMENT: (PermissionCode.FINANCE_VIEW,),
    PermissionCode.FINANCE_REFUND: (PermissionCode.FINANCE_VIEW, PermissionCode.FINANCE_RECORD_PAYMENT),
    PermissionCode.HR_MANAGE: (PermissionCode.HR_VIEW,),
    PermissionCode.USER_MANAGE: (PermissionCode.USER_VIEW,),
    PermissionCode.REPORTS_VIEW: (PermissionCode.DASHBOARD_VIEW,),
    PermissionCode.ANALYTICS_VIEW: (PermissionCode.DASHBOARD_VIEW,),
}


def _expand_aliases(codes: Iterable[PermissionCode]) -> frozenset[PermissionCode]:
    """Return `codes` plus every code implied by an alias relationship."""
    out: set[PermissionCode] = set()
    pending = list(codes)
    while pending:
        code = pending.pop()
        if code in out:
            continue
        out.add(code)
        for implied in PERMISSION_ALIASES.get(code, ()):
            if implied not in out:
                pending.append(implied)
    return frozenset(out)


def effective_permissions_for_role(role: UserRole) -> frozenset[PermissionCode]:
    """Role's default permission set, alias-expanded."""
    return _expand_aliases(ROLE_PERMISSION_DEFAULTS.get(role, ()))


def effective_permissions_for_user(
    role: UserRole,
    explicit_grants: Iterable[str | PermissionCode],
) -> frozenset[PermissionCode]:
    """Final permissions for a user: defaults ∪ explicit_grants, then alias-expanded.

    Unknown strings in `explicit_grants` are silently dropped (a stale grant
    pointing at a removed code should never grant anything).
    """
    base = set(ROLE_PERMISSION_DEFAULTS.get(role, ()))
    for raw in explicit_grants:
        try:
            base.add(PermissionCode(raw))
        except ValueError:
            continue
    return _expand_aliases(base)
