"""Pure unit tests for the Meta-pattern Google Sheet row mapper (no DB/fixtures needed)."""
from datetime import datetime, timezone

import pytest

from app.models.lead import Lead
from app.services.meta_sheet_mapper import (
    CAMPAIGN_MAX_LEN,
    TITLE_MAX_LEN,
    is_meta_permission_placeholder,
    map_sheet_row,
)

# What Meta's Sheets integration writes instead of a name when it can't read the ad account.
_PLACEHOLDER = (
    "You don't have enough permission. Please refer to this help: https://www.facebook.com/business/help/1"
)


def test_meta_row_maps_core_fields_and_uses_leadgen_id():
    external_id, fields = map_sheet_row(
        {
            "id": "lgid_123",
            "created_time": "2026-08-27T11:07:30+0000",
            "full_name": "Test User",
            "email": "t@x.com",
            "phone_number": "+91 87654 30300",
            "city": "Vadodara",
            "what_are_you_looking_for": "3 BHK",
            "campaign_name": "Aug Campaign",
            "platform": "fb",
        }
    )
    assert external_id == "lgid_123"  # Meta leadgen id is the dedup key
    assert fields["contact_name"] == "Test User"
    assert fields["contact_phone"] == "+918765430300"
    assert fields["contact_email"] == "t@x.com"
    assert fields["source"] == "Facebook / Meta"
    assert fields["preferred_location"] == "Vadodara"
    assert fields["interest"] == "3 BHK"
    assert fields["source_created_at"] == datetime(2026, 8, 27, 11, 7, 30, tzinfo=timezone.utc)


def test_instagram_platform_sets_source():
    _eid, fields = map_sheet_row({"full_name": "A", "phone_number": "9876543210", "platform": "instagram"})
    assert fields["source"] == "Instagram"


def test_first_last_name_fallback():
    _eid, fields = map_sheet_row({"first_name": "Jane", "last_name": "Doe", "phone_number": "9876543210"})
    assert fields["contact_name"] == "Jane Doe"


def test_unmapped_columns_preserved_in_notes():
    _eid, fields = map_sheet_row(
        {"full_name": "A", "phone_number": "9876543210", "budget_question": "50L", "utm": "spring"}
    )
    assert "budget_question: 50L" in fields["notes"]
    assert "utm: spring" in fields["notes"]


def test_no_leadgen_id_falls_back_to_fingerprint():
    external_id, _fields = map_sheet_row(
        {"full_name": "X", "phone_number": "9876543210", "created_time": "2026-08-27T10:00:00+0000"}
    )
    assert external_id.startswith("fp_")


def test_empty_row_still_returns_a_key():
    external_id, fields = map_sheet_row({})
    assert external_id.startswith("fp_")
    assert fields["contact_name"] is None


def test_standard_row_ignores_tab_and_keeps_meta_campaign():
    _eid, fields = map_sheet_row(
        {"full_name": "A", "phone_number": "9876543210", "campaign_name": "Aug Campaign", "sheet_tab": "Form 1"}
    )
    assert fields["campaign"] == "Aug Campaign"


@pytest.mark.parametrize(
    "value",
    [
        _PLACEHOLDER,
        "You don't have enough permissions. Please refer to this help page: https://www.facebook.com/bu",
        "you don't have enough permission",
        "You don’t have enough permission. Please refer…",
        "You do not have enough permissions",
        "  You don't have enough permission.",
        _PLACEHOLDER[:CAMPAIGN_MAX_LEN],
    ],
)
def test_permission_placeholder_detected(value):
    assert is_meta_permission_placeholder(value)


@pytest.mark.parametrize(
    "value", ["Vriddhica 2 Lakh Plot Leads campaign", "Permission campaign", "Why you don't have enough permission", "", None]
)
def test_real_names_are_not_placeholders(value):
    assert not is_meta_permission_placeholder(value)


def test_placeholder_campaign_is_treated_as_empty():
    _eid, fields = map_sheet_row({"full_name": "Test User", "phone_number": "9876543210", "campaign_name": _PLACEHOLDER})
    assert fields["campaign"] is None
    assert fields["title"] == "Test User"
    assert "enough permission" not in fields.get("notes", "")


def test_placeholder_adset_ad_form_dropped_from_notes():
    _eid, fields = map_sheet_row(
        {
            "full_name": "A",
            "phone_number": "9876543210",
            "campaign_name": "Real Campaign",
            "adset_name": _PLACEHOLDER,
            "ad_name": _PLACEHOLDER,
            "form_name": _PLACEHOLDER,
        }
    )
    notes = fields["notes"]
    assert "campaign: Real Campaign" in notes
    assert "enough permission" not in notes
    assert "ad set:" not in notes and "\nad:" not in notes and "form:" not in notes


def test_placeholder_falls_through_to_a_real_campaign_alias():
    _eid, fields = map_sheet_row(
        {"full_name": "A", "phone_number": "9876543210", "campaign_name": _PLACEHOLDER, "campaign": "Diwali"}
    )
    assert fields["campaign"] == "Diwali"


def test_agency_placeholder_campaign_uses_the_tab():
    _eid, fields = map_sheet_row(
        {"full_name": "A", "phone": "p:9876543210", "campaign_name": _PLACEHOLDER, "sheet_tab": "Pan India"},
        campaign_from_tab=True,
    )
    assert fields["campaign"] == "Pan India"


def test_campaign_from_tab_without_a_tab_falls_back_to_meta():
    _eid, fields = map_sheet_row(
        {"full_name": "A", "phone_number": "9876543210", "campaign_name": "Meta Camp"}, campaign_from_tab=True
    )
    assert fields["campaign"] == "Meta Camp"


def test_long_campaign_is_clamped_to_the_column():
    long_name = "C" * 300
    _eid, fields = map_sheet_row({"full_name": "A", "phone_number": "9876543210", "campaign_name": long_name})
    assert fields["campaign"] == long_name[:CAMPAIGN_MAX_LEN]
    assert fields["title"].startswith(long_name)  # title keeps the full value; ingest clamps it to 255


def test_length_constants_match_lead_columns():
    assert Lead.__table__.c.campaign.type.length == CAMPAIGN_MAX_LEN
    assert Lead.__table__.c.title.type.length == TITLE_MAX_LEN
