"""Thin Callyzer call-tracking API client (bring-your-own per-tenant token).

Confirmed live against the Callyzer API (v2.2 prod / v2.1 sandbox):
  POST https://api1.callyzer.co/api/v2.2/call-log/history        (production)
  POST https://sandbox.api.callyzer.co/api/v2.1/call-log/history (free sandbox, sandbox=True)
  Authorization: Bearer <token>
  body: { synced_from, synced_to (epoch seconds, UTC; < 180-day window), page_no, page_size }
  → { "result": [ ...call records... ], "message": "Success",
      "total_records": N, "page_no": X, "page_size": Y }

Prod host/version override via CALLYZER_BASE_URL / CALLYZER_API_VERSION env. Errors
surface as `CallyzerError` (`is_auth_error` on 401/403 → connection needs re-auth).
Callyzer rate-limits to ~1 request / 2 seconds (HTTP 429) — we pause between pages and
retry a 429 with backoff. Each call uses its own short-lived AsyncClient; token never logged.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx

# Production is v2.2 on api1.callyzer.co; the free Sandbox is v2.1 on
# sandbox.api.callyzer.co. Both accept the same call-log/history request shape.
# Override the prod host/version via env if Callyzer changes them.
_PROD_BASE = os.environ.get("CALLYZER_BASE_URL", "https://api1.callyzer.co").rstrip("/")
_PROD_VERSION = os.environ.get("CALLYZER_API_VERSION", "v2.2")
_SANDBOX_BASE = "https://sandbox.api.callyzer.co"
_SANDBOX_VERSION = "v2.1"
_PATH = "call-log/history"
# Callyzer documents ~1 request / 2 seconds; pause a hair over 2s between pages.
_RATE_LIMIT_SLEEP = 2.2
_MAX_429_RETRIES = 3
_PAGE_SIZE = 100


class CallyzerError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status

    @property
    def is_auth_error(self) -> bool:
        """True when the token itself is bad (401/403) — the connection needs re-auth."""
        return self.http_status in (401, 403)


class CallyzerClient:
    def __init__(self, token: str, *, sandbox: bool = False) -> None:
        self._token = token or ""
        if sandbox:
            self._base, self._version = _SANDBOX_BASE, _SANDBOX_VERSION
        else:
            self._base, self._version = _PROD_BASE, _PROD_VERSION

    @property
    def _url(self) -> str:
        return f"{self._base}/api/{self._version}/{_PATH}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _post(self, body: dict) -> dict:
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(self._url, json=body, headers=self._headers)
            except httpx.HTTPError as exc:  # network/timeout — transient
                raise CallyzerError(f"Callyzer request failed: {exc}") from exc
            if resp.status_code == 429 and attempt < _MAX_429_RETRIES:
                attempt += 1
                await asyncio.sleep(_RATE_LIMIT_SLEEP * (attempt + 1))
                continue
            data: object = None
            try:
                data = resp.json()
            except ValueError:
                data = None
            if resp.status_code >= 400:
                msg = data.get("message") if isinstance(data, dict) else None
                raise CallyzerError(
                    msg or f"Callyzer API error (HTTP {resp.status_code}).", http_status=resp.status_code
                )
            return data if isinstance(data, dict) else {}

    async def probe(self) -> None:
        """Validate the token with a tiny recent-window request (0 records is still a
        success). Raises CallyzerError (is_auth_error) on a bad token."""
        now = datetime.now(UTC)
        await self._post(
            {
                "synced_from": int((now - timedelta(days=1)).timestamp()),
                "synced_to": int(now.timestamp()),
                "page_no": 1,
                "page_size": 1,
            }
        )

    async def iter_call_history(
        self, *, synced_from: datetime, synced_to: datetime
    ) -> AsyncIterator[dict]:
        """Yield every call record whose sync time is in [synced_from, synced_to],
        paging via page_no/page_size and pausing between pages for the rate limit."""
        sf, st = int(synced_from.timestamp()), int(synced_to.timestamp())
        page = 1
        while True:
            data = await self._post(
                {"synced_from": sf, "synced_to": st, "page_no": page, "page_size": _PAGE_SIZE}
            )
            records = data.get("result")
            records = records if isinstance(records, list) else []
            for rec in records:
                if isinstance(rec, dict):
                    yield rec
            total = data.get("total_records") or 0
            if not records or page * _PAGE_SIZE >= int(total):
                break
            page += 1
            await asyncio.sleep(_RATE_LIMIT_SLEEP)
