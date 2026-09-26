"""Pure unit tests for the header-less (AntTech) positional Google Sheet parser — no DB/network.

Mirrors the real Vriddhica sheet's structure: lead data positional in the LEFT columns in Meta's fixed
order, a wide empty gap, a trailing `lead_status` value, then the field-name header block shifted far RIGHT.
"""
from app.core import google_sheets
from app.core.google_sheets import (
    SHEET_TAB_KEY,
    _data_schema,
    _detect_meta_schema,
    _parse_positional_values,
    read_rows_positional,
)
from app.services.meta_sheet_mapper import map_sheet_row

# The real Vriddhica sheet: 3.5 L / 4.5 L / 6.5 L / Pan India tabs all carry ONE Meta campaign (#46).
_COMBINED = "Vriddhica 3.5 lakh and 4.5 lakh Leads campaign"

# Header block as it appears (misplaced) far to the right of each row.
_HEADER = [
    "id", "created_time", "ad_id", "ad_name", "adset_id", "adset_name", "campaign_id", "campaign_name",
    "form_id", "form_name", "is_organic", "platform", "preferred_time?", "full_name", "phone",
    "street_address", "email", "lead_status",
]


def _row(left: list[str], header: list[str] = _HEADER, gap: int = 30) -> list[str]:
    """One sheet row = left data cols + empty gap + 'CREATED' (the lead_status value) + the header block."""
    return left + [""] * gap + ["CREATED"] + header


def test_detect_schema_finds_the_far_right_header_block():
    left = ["l:1", "2026-08-27T00:37:29-05:00", "ag:1", "Ad", "as:1", "AdSet", "c:1", "Camp",
            "f:1", "Form", "false", "fb", "3pm", "Test User", "p:9876543210", "St", "t@x.com"]
    schema = _detect_meta_schema([_row(left)])
    assert schema is not None
    assert schema[:3] == ["id", "created_time", "ad_id"]
    assert schema[-1] == "lead_status"


def test_data_schema_drops_lead_status():
    assert "lead_status" not in _data_schema(_HEADER)
    assert _data_schema(_HEADER)[-1] == "email"  # last trailing-data field present


def test_parse_positional_maps_core_fields():
    left = ["l:123", "2026-08-27T00:37:29-05:00", "ag:1", "Ad", "as:1", "AdSet", "c:1", "Camp Kolkata",
            "f:1", "Form", "false", "fb", "3pm", "Test User", "p:9876543210", "Vadodara St", "t@x.com"]
    rows = _parse_positional_values([_row(left), _row(left)])
    assert len(rows) == 2
    d = rows[0]
    assert d["id"] == "l:123"
    assert d["full_name"] == "Test User"
    assert d["phone"] == "p:9876543210"
    assert d["email"] == "t@x.com"
    assert d["campaign_name"] == "Camp Kolkata"
    assert d["platform"] == "fb"
    assert "lead_status" not in d  # the trailing outlier is never read as data


def test_pan_india_decoy_phone_is_not_the_contact_phone():
    # A custom-question column ('best_number?') answered with a bare number; the REAL phone carries `p:`.
    header = ["id", "created_time", "ad_id", "ad_name", "adset_id", "adset_name", "campaign_id",
              "campaign_name", "form_id", "form_name", "is_organic", "platform", "best_number?",
              "full_name", "street_address", "phone", "email", "lead_status"]
    left = ["l:777", "2026-08-27T09:50:01-05:00", "ag:1", "Ad", "as:1", "AdSet", "c:1", "Camp", "f:1",
            "Form", "false", "fb", "9999149498", "Jitendra Yadav", "Noida", "p:+919625325428", "jk@x.com"]
    d = _parse_positional_values([_row(left, header=header, gap=20)])[0]
    assert d["phone"] == "p:+919625325428"       # anchored by the p: prefix
    assert d["best_number?"] == "9999149498"      # decoy stays in its own column (→ notes downstream)


def test_no_meta_header_run_yields_no_rows():
    assert _parse_positional_values([["a", "b", "c"], ["x", "y", "z"]]) == []


def test_parsed_row_flows_through_map_sheet_row():
    left = ["l:9", "2026-08-27T00:37:29-05:00", "ag:1", "Ad", "as:1", "AdSet", "c:1", "Camp",
            "f:1", "Form", "false", "ig", "3pm", "Test User", "p:9876543210", "St", "t@x.com"]
    d = _parse_positional_values([_row(left)])[0]
    external_id, fields = map_sheet_row(d)
    assert external_id == "l:9"
    assert fields["contact_name"] == "Test User"
    assert fields["contact_phone"] == "+919876543210"
    assert fields["contact_email"] == "t@x.com"
    assert fields["source"] == "Instagram"  # platform 'ig' → canonical label


# ---- Sheet tab → campaign (#46) ------------------------------------------------------------------

def _left(lead_id: str = "l:1", campaign: str = _COMBINED) -> list[str]:
    return [lead_id, "2026-09-18T03:03:50-05:00", "ag:1", "Ad", "as:1", "AdSet", "c:52510326734875", campaign,
            "f:1", "Form", "false", "fb", "3pm", "Test User", "p:9876543210", "St", "t@x.com"]


def test_parse_positional_attaches_tab_title():
    d = _parse_positional_values([_row(_left())], tab=" 3.5 Lakh Plot ")[0]
    assert d[SHEET_TAB_KEY] == "3.5 Lakh Plot"


def test_parse_positional_without_tab_has_no_tab_key():
    assert SHEET_TAB_KEY not in _parse_positional_values([_row(_left())])[0]


def test_parse_positional_blank_tab_is_ignored():
    assert SHEET_TAB_KEY not in _parse_positional_values([_row(_left())], tab="   ")[0]


class _FakeWorksheet:
    def __init__(self, title: str, values: list[list[str]]):
        self.title = title
        self._values = values

    def get_all_values(self) -> list[list[str]]:
        return self._values


class _FakeClient:
    def __init__(self, worksheets: list[_FakeWorksheet]):
        self._worksheets = worksheets

    def open_by_key(self, _sheet_id: str) -> "_FakeClient":
        return self

    def worksheets(self) -> list[_FakeWorksheet]:
        return self._worksheets


def test_read_rows_positional_tags_each_row_with_its_tab(monkeypatch):
    fake = _FakeClient([
        _FakeWorksheet("3.5 Lakh Plot", [_row(_left("l:1"))]),
        _FakeWorksheet("4.5 Lakh Plot Lead", [_row(_left("l:2")), _row(_left("l:3"))]),
    ])
    monkeypatch.setattr(google_sheets, "_client", lambda: fake)
    rows = read_rows_positional("sheet-id")
    assert [(r["id"], r[SHEET_TAB_KEY]) for r in rows] == [
        ("l:1", "3.5 Lakh Plot"),
        ("l:2", "4.5 Lakh Plot Lead"),
        ("l:3", "4.5 Lakh Plot Lead"),
    ]


def test_agency_campaign_is_the_tab_and_meta_names_stay_in_notes():
    d = _parse_positional_values([_row(_left())], tab="3.5 Lakh Plot")[0]
    _eid, fields = map_sheet_row(d, campaign_from_tab=True)
    assert fields["campaign"] == "3.5 Lakh Plot"
    assert fields["title"] == "3.5 Lakh Plot — Test User"
    notes = fields["notes"]
    assert "sheet tab: 3.5 Lakh Plot" in notes
    assert f"campaign: {_COMBINED}" in notes
    assert "sheet_tab:" not in notes  # attribution line, never an "extra field"


def test_one_meta_campaign_splits_by_tab():
    grid = [_row(_left())]
    campaigns = {
        map_sheet_row(_parse_positional_values(grid, tab=tab)[0], campaign_from_tab=True)[1]["campaign"]
        for tab in ("3.5 Lakh Plot", "4.5 Lakh Plot Lead")
    }
    assert campaigns == {"3.5 Lakh Plot", "4.5 Lakh Plot Lead"}
