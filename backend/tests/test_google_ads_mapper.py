"""Pure unit tests for the Google Ads Lead Form webhook mapper (no DB/fixtures)."""
from app.services.lead_source_mapper import map_google_ads_lead


def _payload(**over):
    base = {
        "lead_id": "GA-123",
        "form_id": 456,
        "campaign_id": 789,
        "gcl_id": "gcl_abc",
        "is_test": False,
        "google_key": "c_secret",
        "user_column_data": [
            {"column_id": "FULL_NAME", "column_name": "Full Name", "string_value": "Dipjyoti Roy"},
            {"column_id": "EMAIL", "column_name": "Email", "string_value": "d@x.com"},
            {"column_id": "PHONE_NUMBER", "column_name": "Phone", "string_value": "+91 8777544380"},
            {"column_id": "CITY", "column_name": "City", "string_value": "Kolkata"},
            {"column_id": "what_is_your_budget", "column_name": "What is your budget?", "string_value": "35 Lakh"},
        ],
    }
    base.update(over)
    return base


def test_maps_core_fields_and_uses_lead_id():
    external_id, fields = map_google_ads_lead(_payload())
    assert external_id == "GA-123"                      # Google lead_id is the dedup key
    assert fields["contact_name"] == "Dipjyoti Roy"
    assert fields["contact_phone"] == "+918777544380"   # normalized to E.164
    assert fields["contact_email"] == "d@x.com"
    assert fields["source"] == "Google Ads"             # canonical SOURCE_LABEL
    assert fields["preferred_location"] == "Kolkata"
    assert fields["title"] == "Dipjyoti Roy"


def test_custom_question_and_attribution_go_to_notes():
    _eid, fields = map_google_ads_lead(_payload())
    notes = fields["notes"]
    assert "What is your budget?: 35 Lakh" in notes     # custom question by its label
    assert "campaign id: 789" in notes                  # attribution
    assert "form id: 456" in notes
    assert "gclid: gcl_abc" in notes


def test_first_last_name_fallback():
    _eid, fields = map_google_ads_lead(_payload(user_column_data=[
        {"column_id": "FIRST_NAME", "string_value": "Jane"},
        {"column_id": "LAST_NAME", "string_value": "Doe"},
        {"column_id": "PHONE_NUMBER", "string_value": "9876543210"},
    ]))
    assert fields["contact_name"] == "Jane Doe"
    assert fields["contact_phone"] == "+919876543210"


def test_no_lead_id_falls_back_to_fingerprint():
    external_id, _fields = map_google_ads_lead(_payload(lead_id="", user_column_data=[
        {"column_id": "PHONE_NUMBER", "string_value": "9876543210"},
    ]))
    assert external_id.startswith("fp_")


def test_empty_columns_still_returns_a_key():
    external_id, fields = map_google_ads_lead({"lead_id": "GA-9", "user_column_data": []})
    assert external_id == "GA-9"
    assert fields["contact_name"] is None
    assert fields["source"] == "Google Ads"
