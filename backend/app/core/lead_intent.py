"""Lead intent — how serious a lead is (High / Medium / Low), rated when the lead's stage changes.

Stored as a short string (no DB enum type — see migrations_tenant/README), NULL = not rated. From
"Booked / Token" onward, and on a closed (won or lost) stage, the intent is settled: a move there doesn't
ask for it and it can't be changed (the UI shows it read-only). The frontend mirrors `intent_locked` in
frontend/src/utils/leadIntent.ts.
"""
from typing import Literal

from app.database.enums import LeadIndustry, PipelineStageCategory
from app.database.pipeline_seed import REAL_ESTATE_STAGES

LeadIntent = Literal["high", "medium", "low"]
LEAD_INTENTS: tuple[str, ...] = ("high", "medium", "low")
# Leads-list filter token for "no intent yet".
INTENT_NOT_RATED = "none"
# Where an intent change came from (lead_intent_changes.source).
INTENT_SOURCES: tuple[str, ...] = ("stage_change", "bulk", "quick_set", "created", "import")

INTENT_LABEL = {"high": "High", "medium": "Medium", "low": "Low"}

# Real-estate pipeline position of "Booked / Token": from here on the intent is fixed.
_REAL_ESTATE_LOCK_POSITION = next(p for (_ind, p, code, *_rest) in REAL_ESTATE_STAGES if code == "booked")


def intent_locked(industry: LeadIndustry | str, position: int, category: PipelineStageCategory | str) -> bool:
    """True when a lead at this stage keeps its intent as is (not asked on the move, not editable)."""
    if str(category) in (PipelineStageCategory.closed_won.value, PipelineStageCategory.closed_lost.value):
        return True
    return str(industry) == LeadIndustry.real_estate.value and position >= _REAL_ESTATE_LOCK_POSITION


def stage_locks_intent(stage) -> bool:
    """`intent_locked` for a PipelineStage row."""
    return intent_locked(stage.industry, stage.position, stage.category)


# Sheet spellings people already use for the same idea (CSV import).
_INTENT_SYNONYMS = {"hot": "high", "warm": "medium", "cold": "low"}


def normalize_intent(raw: str | None) -> str | None:
    """"High" / " high " / "Hot" → "high"; blank → None; anything else raises ValueError (CSV import)."""
    if raw is None or not str(raw).strip():
        return None
    value = str(raw).strip().lower()
    value = _INTENT_SYNONYMS.get(value, value)
    if value not in LEAD_INTENTS:
        raise ValueError("Intent must be High, Medium or Low.")
    return value
