"""Pure unit tests for the 99acres → FlexCRM mapper (no DB/fixtures needed)."""
from datetime import datetime, timezone

from app.services.lead_source_mapper import map_99acres_lead, parse_received_date


def test_parse_received_date_live_push_format_ist_to_utc():
    # 99acres live push: "YYYY-MM-DD HH:MM:SS", India-local (IST = UTC+5:30).
    dt = parse_received_date("2026-08-27 16:37:30")
    assert dt == datetime(2026, 8, 27, 11, 7, 30, tzinfo=timezone.utc)


def test_parse_received_date_dashboard_export_format():
    # Dashboard export: "MM/DD/YYYY hh:mm AM/PM" (also IST).
    dt = parse_received_date("07/13/2026 12:39 AM")
    assert dt == datetime(2026, 7, 12, 19, 9, 0, tzinfo=timezone.utc)


def test_parse_received_date_iso_with_offset_preserved():
    dt = parse_received_date("2026-08-27T16:37:30+05:30")
    assert dt == datetime(2026, 8, 27, 11, 7, 30, tzinfo=timezone.utc)


def test_parse_received_date_unparseable_or_empty_returns_none():
    assert parse_received_date("garbage") is None
    assert parse_received_date("") is None
    assert parse_received_date(None) is None


def test_map_99acres_lead_sets_source_created_at_and_location():
    external_id, fields = map_99acres_lead(
        {
            "lead_id": "602fb900b17fda0008c83bc1",
            "Name": "testlead",
            "ContactNo": "91-8765430300",
            "InterestedIn": "Ultima Lifestyle",
            "City": "Vadodara",
            "ResCom": "R",
            "Bhk": "0 BHK",
            "ReceivedDate": "2026-08-27 16:37:30",
        }
    )
    assert external_id == "602fb900b17fda0008c83bc1"
    assert fields["source_created_at"] == datetime(2026, 8, 27, 11, 7, 30, tzinfo=timezone.utc)
    assert fields["preferred_location"] == "Vadodara"
    assert fields["contact_phone"] == "+918765430300"
    assert fields["source"] == "99acres"


def test_map_99acres_lead_without_received_date_omits_source_created_at():
    _external_id, fields = map_99acres_lead({"Name": "x", "ContactNo": "9876543210"})
    assert "source_created_at" not in fields
