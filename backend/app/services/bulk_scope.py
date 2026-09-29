"""Hold back per-row side effects during a bulk write (one CSV import request — the browser sends big files as
50-row chunks): realtime events and reporting-cache invalidation happen ONCE when the scope ends, instead of
once per row.

Per row, `LeadService.create_lead` broadcasts `lead.created` and wipes the reporting cache (a full Redis
SCAN). For a 300-row import that was 330 broadcasts + 660 SCAN-and-delete passes: every open Leads page and
Dashboard in the org refetched every ~2.5 s for the whole import (flicker, 429s) and the import itself slowed
down. Inside `bulk_side_effects()`:

- `realtime_manager.broadcast` only counts events, per (org, event, reason); on exit ONE event per group is
  sent with payload `{"bulk": True, "count": n}` (+ `reason` when the events carried one). Event names are
  unchanged, so every subscriber (and tabs on an older frontend build) still refreshes — once.
- `ServiceBase.invalidate_reporting_cache` only marks the cache dirty; it is wiped once on exit.

The state lives in a ContextVar, so it's scoped to the current request's task — concurrent requests are
unaffected. The flush runs in `finally` (rows committed before a failure still get their event) and never
raises. User-targeted sends (`broadcast_to_user`) are not held back.
"""
from __future__ import annotations

import contextvars
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from app.core.cache import cache_client
from app.core.logging import get_logger

logger = get_logger(__name__)

REPORTING_CACHE_PREFIXES = ("dashboard:", "analytics:")


@dataclass
class PendingSideEffects:
    # (org_id, event name, reason or None) -> number of held-back events
    events: dict[tuple[UUID, str, str | None], int] = field(default_factory=dict)
    invalidate_cache: bool = False

    def hold_event(self, org_id: UUID, payload: dict) -> None:
        event = str(payload.get("event") or "")
        body = payload.get("payload")
        reason = body.get("reason") if isinstance(body, dict) and isinstance(body.get("reason"), str) else None
        key = (org_id, event, reason)
        self.events[key] = self.events.get(key, 0) + 1


_pending: contextvars.ContextVar[PendingSideEffects | None] = contextvars.ContextVar(
    "bulk_side_effects", default=None
)


def pending_side_effects() -> PendingSideEffects | None:
    """The active bulk scope of this request, or None (side effects happen immediately)."""
    return _pending.get()


async def invalidate_reporting_cache_now() -> None:
    for prefix in REPORTING_CACHE_PREFIXES:
        await cache_client.delete_pattern(prefix)


@asynccontextmanager
async def bulk_side_effects() -> AsyncIterator[PendingSideEffects]:
    """See the module docstring. Nested scopes join the outermost one."""
    outer = _pending.get()
    if outer is not None:
        yield outer
        return
    state = PendingSideEffects()
    token = _pending.set(state)
    try:
        yield state
    finally:
        _pending.reset(token)
        await _flush(state)


async def _flush(state: PendingSideEffects) -> None:
    # Cache first, so clients refetching on the event below read fresh numbers.
    if state.invalidate_cache:
        try:
            await invalidate_reporting_cache_now()
        except Exception:  # noqa: BLE001 — a flush failure must never fail the (already committed) import
            logger.warning("bulk scope: reporting cache invalidation failed", exc_info=True)
    if not state.events:
        return
    from app.services.realtime import realtime_manager  # local: realtime imports this module

    for (org_id, event, reason), count in state.events.items():
        body: dict = {"bulk": True, "count": count}
        if reason is not None:
            body["reason"] = reason
        try:
            await realtime_manager.broadcast({"event": event, "payload": body}, org_id=org_id)
        except Exception:  # noqa: BLE001
            logger.warning("bulk scope: broadcast of %s failed", event, exc_info=True)
