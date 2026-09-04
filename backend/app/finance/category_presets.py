"""Curated income/expense category presets per finance business mode.

Seeded lazily per-org (idempotent) by FinanceCategoryService.ensure_seeded once
the org's finance_business_mode is known. `hybrid` = de-duplicated union of the
builder + broker + general lists. Not exhaustive — an org adds custom categories
on top and can disable presets it doesn't use.
"""
from __future__ import annotations

from app.database.enums import FinanceBusinessMode, FinanceCategoryKind

# (name, group_label) per category — group_label just drives UI grouping.
_Preset = tuple[str, str]

_GENERAL_EXPENSES: list[_Preset] = [
    ("Office Rent", "Administration"),
    ("Salaries & Wages", "Payroll"),
    ("Utilities (Electricity/Water)", "Administration"),
    ("Internet & Telephone", "Administration"),
    ("Office Supplies", "Administration"),
    ("Marketing & Advertising", "Sales & Marketing"),
    ("Travel & Conveyance", "Operations"),
    ("Professional Fees (Legal/CA)", "Professional"),
    ("Bank Charges", "Finance"),
    ("Repairs & Maintenance", "Operations"),
    ("Software Subscriptions", "Operations"),
    ("Government & Statutory Fees", "Statutory"),
    ("Miscellaneous", "Other"),
]

_RE_BUILDER_EXPENSES: list[_Preset] = [
    ("Land Purchase / Acquisition", "Land"),
    ("Stamp Duty & Registration", "Land"),
    ("Govt Approvals & RERA Fees", "Approvals & Statutory"),
    ("Construction Material (Cement/Steel)", "Construction"),
    ("Labour & Contractor Payments", "Construction"),
    ("Architect / Structural Consultant Fees", "Professional"),
    ("Legal & Documentation", "Professional"),
    ("Machinery & Equipment Hire", "Construction"),
    ("Site Utilities & Temporary Infra", "Site Overheads"),
    ("Project Office Overheads", "Site Overheads"),
    ("Sales & Marketing (Brochures/Branding)", "Sales & Marketing"),
    ("Broker / Channel-Partner Commission", "Sales & Marketing"),
    ("Interest & Finance Charges", "Finance"),
    ("Miscellaneous", "Other"),
]

_RE_BROKER_EXPENSES: list[_Preset] = [
    ("Office Rent", "Administration"),
    ("Field Staff Salaries & Incentives", "Payroll"),
    ("Telecalling / Lead-Gen Costs", "Sales & Marketing"),
    ("Portal Subscriptions (99acres/MagicBricks)", "Sales & Marketing"),
    ("Digital Ads (Meta/Google)", "Sales & Marketing"),
    ("Sub-broker / Referral Payouts", "Sales & Marketing"),
    ("Printing & Promotional", "Sales & Marketing"),
    ("Travel & Conveyance", "Operations"),
    ("Client Entertainment", "Operations"),
    ("CRM / Software Subscriptions", "Operations"),
    ("Professional Fees", "Professional"),
    ("Miscellaneous", "Other"),
]

_GENERAL_INCOME: list[_Preset] = [
    ("Service Revenue", "Operating"),
    ("Product Sales", "Operating"),
    ("Commission Earned", "Commission"),
    ("Interest Income", "Financial"),
    ("Other Income", "Other"),
]

_RE_BUILDER_INCOME: list[_Preset] = [
    ("Unit Sale Proceeds", "Sales"),
    ("Booking / Token Advance", "Sales"),
    ("Parking Charges", "Sales"),
    ("Preferential Location Charges", "Sales"),
    ("Maintenance Deposit", "Collections"),
    ("Interest on Delayed Payment", "Financial"),
    ("Other Project Income", "Other"),
]

_RE_BROKER_INCOME: list[_Preset] = [
    ("Brokerage Income", "Commission"),
    ("Referral Income", "Commission"),
    ("Consultation Fees", "Professional"),
    ("Other Income", "Other"),
]

_BY_MODE: dict[FinanceBusinessMode, dict[FinanceCategoryKind, list[_Preset]]] = {
    FinanceBusinessMode.general: {
        FinanceCategoryKind.expense: _GENERAL_EXPENSES,
        FinanceCategoryKind.income: _GENERAL_INCOME,
    },
    FinanceBusinessMode.re_builder: {
        FinanceCategoryKind.expense: _RE_BUILDER_EXPENSES,
        FinanceCategoryKind.income: _RE_BUILDER_INCOME,
    },
    FinanceBusinessMode.re_broker: {
        FinanceCategoryKind.expense: _RE_BROKER_EXPENSES,
        FinanceCategoryKind.income: _RE_BROKER_INCOME,
    },
}


def _dedup_union(*lists: list[_Preset]) -> list[_Preset]:
    seen: set[str] = set()
    out: list[_Preset] = []
    for lst in lists:
        for name, group in lst:
            if name not in seen:
                seen.add(name)
                out.append((name, group))
    return out


_BY_MODE[FinanceBusinessMode.hybrid] = {
    FinanceCategoryKind.expense: _dedup_union(
        _RE_BUILDER_EXPENSES, _RE_BROKER_EXPENSES, _GENERAL_EXPENSES
    ),
    FinanceCategoryKind.income: _dedup_union(
        _RE_BUILDER_INCOME, _RE_BROKER_INCOME, _GENERAL_INCOME
    ),
}


def presets_for(mode: FinanceBusinessMode, kind: FinanceCategoryKind) -> list[_Preset]:
    """(name, group_label) presets for a mode + kind. Empty if none."""
    return _BY_MODE.get(mode, _BY_MODE[FinanceBusinessMode.general]).get(kind, [])
