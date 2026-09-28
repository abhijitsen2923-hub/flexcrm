"""Pure helpers for lead campaign names — no tenant data, no DB.

Every tenant keeps its OWN campaign list (services/campaigns.py). These helpers only define how two
spellings are compared:

- `campaign_key` — the identity: trimmed, inner whitespace collapsed, lower-cased. "PAN India X" and
  "Pan  India x" are the same campaign; matching on it is automatic.
- `loose_key` + `suggest_merges` — near-duplicates that differ by spaces/punctuation or are very similar
  ("Promo 4.5 L" / "Promo 4.5L") are only SUGGESTED to a manager, never merged automatically. Names whose
  numbers differ ("3.5L" vs "4.5L") are never suggested.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

CAMPAIGN_NAME_MAX_LEN = 120  # leads.campaign is String(120)
_SIMILARITY = 0.85
_MAX_SIMILARITY_ITEMS = 300  # the pairwise "similar" pass is skipped for larger lists (exact loose matches still run)
_MAX_SUGGESTIONS = 100  # a manager works through a handful at a time; bounds the work on pathological lists


def clean_display(raw: object) -> str | None:
    """Trim + collapse every whitespace run (tabs, non-breaking spaces, …) to one space; clamp to the
    column length. Empty → None."""
    if raw is None:
        return None
    text = " ".join(str(raw).split())[:CAMPAIGN_NAME_MAX_LEN].strip()
    return text or None


def campaign_key(raw: object) -> str:
    """Identity key: the cleaned name, lower-cased ('' for empty). Mirrors frontend utils/campaigns.ts."""
    return (clean_display(raw) or "").lower()


def loose_key(raw: object) -> str:
    """Key without spaces/punctuation — only for SUGGESTIONS. `\\W` keeps letters of any script."""
    return re.sub(r"[\W_]+", "", campaign_key(raw))


def numbers(raw: object) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+(?:\.\d+)?", campaign_key(raw)))


def near_duplicate_reason(a: object, b: object) -> str | None:
    """Why two different campaigns look like the same one, or None."""
    key_a, key_b = campaign_key(a), campaign_key(b)
    loose_a, loose_b = loose_key(a), loose_key(b)
    if not loose_a or not loose_b or key_a == key_b:
        return None
    if loose_a == loose_b:
        return "spacing_punctuation"
    if numbers(a) != numbers(b):
        return None
    return "similar" if _similar_loose(loose_a, loose_b) else None


def _similar_loose(loose_a: str, loose_b: str) -> bool:
    """Two different loose keys (same numbers) that look alike: one extends the other, or they're ≥85%
    similar. Cheap upper bounds run first — this is called pairwise, so it must stay fast."""
    shorter, longer = sorted((loose_a, loose_b), key=len)
    if len(shorter) >= 6 and longer.startswith(shorter):
        return True
    # ratio() can never exceed 2*len(shorter)/(total length): skip pairs whose lengths already rule it out.
    if 2 * len(shorter) < _SIMILARITY * (len(shorter) + len(longer)):
        return False
    matcher = SequenceMatcher(None, loose_a, loose_b, autojunk=False)
    return matcher.quick_ratio() >= _SIMILARITY and matcher.ratio() >= _SIMILARITY


def suggest_merges(items: list[tuple[str, str, int]]) -> list[dict]:
    """Candidate merges among a tenant's campaigns: items are (id, name, lead_count). Each suggestion keeps
    the campaign with more leads. Deterministic for a given input order (by reason, then names); at most
    _MAX_SUGGESTIONS. Pure CPU — callers on the event loop should run it in a worker thread."""
    suggestions: list[dict] = []
    seen_pairs: set[frozenset[str]] = set()

    def add(a: tuple[str, str, int], b: tuple[str, str, int], reason: str) -> None:
        pair = frozenset((a[0], b[0]))
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        keep, merge = (a, b) if (a[2], b[1].lower()) >= (b[2], a[1].lower()) else (b, a)
        suggestions.append({"keep_id": keep[0], "merge_id": merge[0], "reason": reason})

    # Keys are computed once per name (the pairwise pass below must not redo regex work per pair).
    prepared = [(item, campaign_key(item[1]), loose_key(item[1]), numbers(item[1])) for item in items]

    # 1) exact loose-key buckets — O(n)
    buckets: dict[str, list[tuple[str, str, int]]] = {}
    for item, _key, loose, _nums in prepared:
        if loose:
            buckets.setdefault(loose, []).append(item)
    for bucket in buckets.values():
        bucket.sort(key=lambda i: (-i[2], i[1].lower()))
        for other in bucket[1:]:
            add(bucket[0], other, "spacing_punctuation")

    # 2) similar names sharing the same numbers — pairwise within a number bucket, capped
    if len(items) <= _MAX_SIMILARITY_ITEMS:
        by_numbers: dict[tuple[str, ...], list[tuple[tuple[str, str, int], str, str]]] = {}
        for item, key, loose, nums in prepared:
            if loose:
                by_numbers.setdefault(nums, []).append((item, key, loose))
        for group in by_numbers.values():
            for i, (a, key_a, loose_a) in enumerate(group):
                if len(suggestions) >= _MAX_SUGGESTIONS:
                    break
                for b, key_b, loose_b in group[i + 1:]:
                    if key_a != key_b and loose_a != loose_b and _similar_loose(loose_a, loose_b):
                        add(a, b, "similar")

    names = {item[0]: item[1].lower() for item in items}
    suggestions.sort(key=lambda s: (s["reason"] != "spacing_punctuation", names[s["keep_id"]], names[s["merge_id"]]))
    return suggestions[:_MAX_SUGGESTIONS]


def closest_matches(raw: object, names: list[str], limit: int = 3) -> list[str]:
    """Up to `limit` existing names that look like `raw` (for a helpful 'did you mean' hint)."""
    target = loose_key(raw)
    if not target:
        return []
    scored = [
        (SequenceMatcher(None, target, loose_key(name)).ratio(), name)
        for name in names
        if loose_key(name)
    ]
    return [name for score, name in sorted(scored, key=lambda s: (-s[0], s[1].lower())) if score >= 0.6][:limit]
