"""Pure campaign-name rules (app/core/campaign_names.py): what counts as the SAME campaign (automatic) and
what is only SUGGESTED to a manager as a likely duplicate. Neutral names only — no tenant data."""
from __future__ import annotations

from app.core.campaign_names import (
    CAMPAIGN_NAME_MAX_LEN,
    campaign_key,
    clean_display,
    closest_matches,
    loose_key,
    near_duplicate_reason,
    suggest_merges,
)


def test_clean_display_trims_and_collapses_every_whitespace_run():
    assert clean_display("  Monsoon \t  Offer  2026 \n") == "Monsoon Offer 2026"
    assert clean_display("Monsoon Offer") == "Monsoon Offer"


def test_clean_display_blank_is_none():
    for raw in (None, "", "   ", "\t\n"):
        assert clean_display(raw) is None


def test_clean_display_clamps_to_the_column_length():
    cleaned = clean_display("x" * 500)
    assert cleaned is not None and len(cleaned) == CAMPAIGN_NAME_MAX_LEN
    # A clamp that lands on a space never leaves a trailing blank.
    assert clean_display("a" * (CAMPAIGN_NAME_MAX_LEN - 1) + " tail") == "a" * (CAMPAIGN_NAME_MAX_LEN - 1)


def test_campaign_key_ignores_case_and_extra_spaces_only():
    assert campaign_key("Monsoon  OFFER") == campaign_key(" monsoon offer ") == "monsoon offer"
    # Punctuation / missing spaces are NOT the same campaign automatically (only suggested).
    assert campaign_key("Promo 4.5L") != campaign_key("Promo 4.5 L")
    assert campaign_key(None) == campaign_key("  ") == ""


def test_loose_key_keeps_non_latin_letters():
    assert loose_key("দুর্গা পূজা") != ""
    assert loose_key("Promo-4.5 L") == loose_key("promo 45l")


def test_near_duplicate_reasons():
    assert near_duplicate_reason("Promo 4.5 L", "Promo 4.5L") == "spacing_punctuation"
    assert near_duplicate_reason("Spring Offer", "Spring Offers") == "similar"
    # Different numbers are different products — never suggested.
    assert near_duplicate_reason("Promo 3.5L", "Promo 4.5L") is None
    # Same numbers + one name extends the other → suggested ("2L" / "2 Lacs").
    assert near_duplicate_reason("Promo 2L", "Promo 2 Lacs") == "similar"
    # Same key is the same campaign already, not a "suggestion".
    assert near_duplicate_reason("Spring Offer", "spring  offer") is None
    assert near_duplicate_reason("Alpha", "Omega Launch") is None
    assert near_duplicate_reason("", "Promo") is None


def test_suggest_merges_keeps_the_campaign_with_more_leads():
    items = [("a", "Promo 4.5L", 3), ("b", "Promo 4.5 L", 10), ("c", "Promo 3.5L", 50)]
    assert suggest_merges(items) == [{"keep_id": "b", "merge_id": "a", "reason": "spacing_punctuation"}]


def test_suggest_merges_never_pairs_different_numbers():
    items = [("a", "Plot 2L", 1), ("b", "Plot 3.5L", 1), ("c", "Plot 4.5L", 1), ("d", "Plot 6.5L", 1)]
    assert suggest_merges(items) == []


def test_suggest_merges_is_deterministic_and_pairs_once():
    items = [
        ("a", "Spring Offer", 2),
        ("b", "Spring Offers", 2),
        ("c", "Spring-Offer", 1),
    ]
    first = suggest_merges(items)
    assert first == suggest_merges(list(reversed(items)))
    pairs = [frozenset((s["keep_id"], s["merge_id"])) for s in first]
    assert len(pairs) == len(set(pairs))
    # The exact loose-key match comes first; ties keep the alphabetically first name.
    assert first[0] == {"keep_id": "a", "merge_id": "c", "reason": "spacing_punctuation"}
    assert {"keep_id": "a", "merge_id": "b", "reason": "similar"} in first


def test_closest_matches_offers_did_you_mean():
    names = ["Monsoon Offer", "Winter Launch", "Expo Fair"]
    assert closest_matches("monsoon ofer", names)[0] == "Monsoon Offer"
    assert closest_matches("zzzz", names) == []
    assert closest_matches("", names) == []
