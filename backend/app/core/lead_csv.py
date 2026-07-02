"""Per-business-type lead CSV schema — the single source of truth for the
import template, the CSV importer, and the CSV export.

Add or change a column in ONE place here and the downloadable template, the
import parser, and the export sheet all stay consistent. Each vertical
(education / travel / real_estate) gets its own column set: the shared columns
plus a few vertical-specific ones (e.g. Destination for travel, property/budget
fields for real estate).
"""
from dataclasses import dataclass, field

from app.database.enums import LeadIndustry


@dataclass(frozen=True)
class CsvColumn:
    key: str                       # LeadCreate/Lead attribute name (or "stage")
    header: str                    # column header shown in template + export
    aliases: frozenset[str] = frozenset()  # accepted import headers (lowercased)
    kind: str = "str"              # str | decimal | int | date | currency | stage
    sample: str = ""               # example value used in the downloadable template

    def all_aliases(self) -> frozenset[str]:
        # The header itself (lowercased) is always an accepted alias.
        return self.aliases | {self.header.lower(), self.key}


# --- Shared columns (every vertical) -------------------------------------
_COMMON: list[CsvColumn] = [
    CsvColumn("title", "Title", frozenset({"subject", "lead_title"}), sample="New enquiry"),
    CsvColumn("contact_name", "Contact name", frozenset({"name", "lead_name", "contact"}), sample="Priya Nair"),
    CsvColumn("contact_email", "Email", frozenset({"contact_email"}), sample="priya.nair@gmail.com"),
    CsvColumn("contact_phone", "Phone", frozenset({"mobile"}), sample="+91 99876 54321"),
    CsvColumn("company_name", "Company / Organization", frozenset({"company", "organization", "org"}), sample=""),
    CsvColumn("source", "Source", frozenset({"lead_source"}), sample="Referral"),
    CsvColumn("value", "Value", frozenset({"amount", "deal_value"}), kind="decimal", sample="150000"),
    CsvColumn("currency", "Currency", frozenset({"currency_code"}), kind="currency", sample="INR"),
    CsvColumn("probability", "Probability (%)", frozenset({"prob"}), kind="int", sample="60"),
    CsvColumn("expected_close_date", "Expected close", frozenset({"close_date", "expected_close"}), kind="date", sample="30-06-2026"),
    CsvColumn("stage", "Stage", frozenset({"stage_code", "lead_stage", "status"}), kind="stage", sample=""),
]

# --- Vertical-specific columns -------------------------------------------
_VERTICAL: dict[LeadIndustry, list[CsvColumn]] = {
    LeadIndustry.education: [
        CsvColumn("interest", "Course", frozenset({"interest", "course_destination"}), sample="MBA - Marketing"),
    ],
    LeadIndustry.travel: [
        CsvColumn("interest", "Destination", frozenset({"interest", "course_destination"}), sample="Bali - 7 days"),
    ],
    LeadIndustry.real_estate: [
        CsvColumn("interest", "Interest", frozenset(), sample="2BHK near city center"),
        CsvColumn("property_type", "Property type", frozenset({"type"}), sample="Apartment"),
        CsvColumn("budget_min", "Budget min", frozenset({"min budget"}), kind="decimal", sample="4000000"),
        CsvColumn("budget_max", "Budget max", frozenset({"max budget"}), kind="decimal", sample="6000000"),
        CsvColumn("preferred_location", "Preferred location", frozenset({"location"}), sample="Whitefield"),
        CsvColumn("possession_preference", "Possession preference", frozenset({"possession"}), sample="Ready to move"),
    ],
}

# Sample rows for the downloadable template (2 per vertical), keyed by column key.
# Missing keys fall back to the column's `sample`.
_EXTRA_SAMPLE_ROWS: dict[LeadIndustry, list[dict[str, str]]] = {
    LeadIndustry.education: [
        {"title": "B.Com admission query", "contact_name": "Kavya Reddy", "contact_email": "kavya.reddy@gmail.com",
         "contact_phone": "+91 96543 21098", "source": "Education Fair", "value": "75000", "probability": "65",
         "interest": "B.Com - General", "expected_close_date": "01-07-2026"},
    ],
    LeadIndustry.travel: [
        {"title": "Maldives family vacation", "contact_name": "Aman Verma", "contact_email": "aman.verma@yahoo.com",
         "contact_phone": "+91 90123 45678", "source": "Walk-in", "value": "250000", "probability": "55",
         "interest": "Maldives - 5 days", "expected_close_date": "20-07-2026"},
    ],
    LeadIndustry.real_estate: [
        {"title": "3BHK premium enquiry", "contact_name": "Rohit Sharma", "contact_email": "rohit.sharma@gmail.com",
         "contact_phone": "+91 98300 12345", "source": "Website", "value": "8500000", "probability": "50",
         "interest": "3BHK premium", "property_type": "Apartment", "budget_min": "7500000", "budget_max": "9000000",
         "preferred_location": "New Town, Kolkata", "possession_preference": "Immediate / Ready to move",
         "expected_close_date": "10-09-2026"},
    ],
}


def _industry_or_default(industry: LeadIndustry | None) -> LeadIndustry:
    return industry if industry in _VERTICAL else LeadIndustry.education


def columns_for(industry: LeadIndustry | None) -> list[CsvColumn]:
    """Ordered CSV columns for a vertical: shared columns + vertical-specific."""
    return _COMMON + _VERTICAL[_industry_or_default(industry)]


def import_columns_for(industry: LeadIndustry | None) -> list[CsvColumn]:
    """Columns the importer accepts (same as columns_for)."""
    return columns_for(industry)


def build_template_csv(industry: LeadIndustry | None) -> tuple[str, str]:
    """Return (csv_body, filename) for the vertical's downloadable template."""
    import csv
    import io

    ind = _industry_or_default(industry)
    cols = columns_for(ind)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c.header for c in cols])
    # One "column sample" row + any richer example rows.
    sample_rows = [{c.key: c.sample for c in cols}, *(_EXTRA_SAMPLE_ROWS.get(ind, []))]
    for sr in sample_rows:
        writer.writerow([sr.get(c.key, c.sample) for c in cols])
    return buf.getvalue(), f"leads-import-template-{ind.value}.csv"
