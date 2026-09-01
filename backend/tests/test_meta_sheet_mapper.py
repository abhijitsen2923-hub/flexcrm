"""Pure unit tests for the Meta-pattern Google Sheet row mapper (no DB/fixtures needed)."""
from datetime import datetime, timezone

from app.services.meta_sheet_mapper import map_sheet_row


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
    assert fields["source"] == "facebook"
    assert fields["preferred_location"] == "Vadodara"
    assert fields["interest"] == "3 BHK"
    assert fields["source_created_at"] == datetime(2026, 8, 27, 11, 7, 30, tzinfo=timezone.utc)


def test_instagram_platform_sets_source():
    _eid, fields = map_sheet_row({"full_name": "A", "phone_number": "9876543210", "platform": "instagram"})
    assert fields["source"] == "instagram"


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
