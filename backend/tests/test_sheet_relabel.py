"""Pure unit tests for the Google Sheet self-heal (#46): which already-ingested leads get their
campaign/title rewritten on a re-poll. No DB — `relabel_changes` is a pure function."""
from app.core.google_sheets import SHEET_TAB_KEY
from app.services.meta_sheet_mapper import (
    CAMPAIGN_MAX_LEN,
    legacy_campaign_and_title,
    map_sheet_row,
    relabel_changes,
)

_COMBINED = "Vriddhica 3.5 lakh and 4.5 lakh Leads campaign"
_PLACEHOLDER = (
    "You don't have enough permission. Please refer to this help: https://www.facebook.com/business/help/1"
)


def _agency_row(tab: str = "3.5 Lakh Plot", campaign: str = _COMBINED) -> dict:
    return {
        "id": "l:1",
        "created_time": "2026-09-18T03:03:50-05:00",
        "campaign_name": campaign,
        "adset_name": "AdSet",
        "platform": "fb",
        "full_name": "Test User",
        "phone": "p:9876543210",
        SHEET_TAB_KEY: tab,
    }


def _standard_row(campaign: str = "Aug Campaign") -> dict:
    return {"id": "lg1", "full_name": "Test User", "phone_number": "9876543210", "campaign_name": campaign}


def _heal(row: dict, *, agency: bool = True, campaign: str | None, title: str | None) -> dict:
    _eid, fields = map_sheet_row(row, campaign_from_tab=agency)
    return relabel_changes(row, fields, current_campaign=campaign, current_title=title)


def test_legacy_values_match_what_the_old_mapper_stored():
    assert legacy_campaign_and_title(_agency_row()) == (_COMBINED, f"{_COMBINED} — Test User")


def test_untouched_agency_lead_moves_to_its_tab():
    assert _heal(_agency_row(), campaign=_COMBINED, title=f"{_COMBINED} — Test User") == {
        "campaign": "3.5 Lakh Plot",
        "title": "3.5 Lakh Plot — Test User",
    }


def test_hand_edited_campaign_is_left_alone_but_title_still_heals():
    changes = _heal(_agency_row(), campaign="Walk-in", title=f"{_COMBINED} — Test User")
    assert changes == {"title": "3.5 Lakh Plot — Test User"}


def test_hand_edited_title_is_left_alone_but_campaign_still_heals():
    assert _heal(_agency_row(), campaign=_COMBINED, title="VIP buyer") == {"campaign": "3.5 Lakh Plot"}


def test_relabel_is_idempotent():
    row = _agency_row()
    first = _heal(row, campaign=_COMBINED, title=f"{_COMBINED} — Test User")
    assert _heal(row, campaign=first["campaign"], title=first["title"]) == {}


def test_standard_lead_is_unchanged():
    assert _heal(_standard_row(), agency=False, campaign="Aug Campaign", title="Aug Campaign — Test User") == {}


def test_standard_placeholder_is_cleared():
    changes = _heal(
        _standard_row(_PLACEHOLDER),
        agency=False,
        campaign=_PLACEHOLDER[:CAMPAIGN_MAX_LEN],
        title=f"{_PLACEHOLDER} — Test User",
    )
    assert changes == {"campaign": None, "title": "Test User"}


def test_placeholder_is_cleared_even_if_the_sheet_cell_changed():
    # The sheet now carries a real name, but the lead still holds the placeholder from an older import.
    changes = _heal(
        _standard_row("Aug Campaign"),
        agency=False,
        campaign=_PLACEHOLDER[:CAMPAIGN_MAX_LEN],
        title="Aug Campaign — Test User",
    )
    assert changes == {"campaign": "Aug Campaign"}


def test_backfilled_long_campaign_still_matches_legacy():
    long_name = "Vriddhica " + "x" * 200  # stored clamped to 120 by ingest / backfill_sheet_campaign.py
    changes = _heal(_agency_row(campaign=long_name), campaign=long_name[:CAMPAIGN_MAX_LEN], title=f"{long_name} — Test User")
    assert changes == {"campaign": "3.5 Lakh Plot", "title": "3.5 Lakh Plot — Test User"}


def test_agency_lead_without_a_meta_campaign_gets_its_tab():
    assert _heal(_agency_row(campaign=""), campaign=None, title="Test User") == {
        "campaign": "3.5 Lakh Plot",
        "title": "3.5 Lakh Plot — Test User",
    }


def test_same_leadgen_id_in_two_tabs_converges():
    """The sync relabels only on a lead's FIRST row in sheet order: over repeated polls the lead settles
    on that tab, and the other tab's row can never take it over (even if the tabs were reordered)."""
    row_a, row_b = _agency_row("3.5 Lakh Plot"), _agency_row("4.5 Lakh Plot Lead")
    campaign, title = _COMBINED, f"{_COMBINED} — Test User"
    for _poll in range(3):
        changes = _heal(row_a, campaign=campaign, title=title)
        campaign, title = changes.get("campaign", campaign), changes.get("title", title)
    assert (campaign, title) == ("3.5 Lakh Plot", "3.5 Lakh Plot — Test User")
    assert _heal(row_b, campaign=campaign, title=title) == {}


def test_legacy_campaign_stored_in_another_case_still_heals():
    # The tenant's campaign list keeps ONE spelling per campaign (case / extra spaces ignored), so an
    # untouched legacy lead may now hold the combined name in a different case — it must still heal.
    changes = _heal(_agency_row(), campaign="  " + _COMBINED.upper().replace(" ", "  "), title="VIP buyer")
    assert changes == {"campaign": "3.5 Lakh Plot"}


def test_tab_name_in_another_case_is_not_rewritten():
    assert _heal(_agency_row(), campaign="3.5 LAKH plot", title="VIP buyer") == {}
