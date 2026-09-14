"""Thin Callyzer call-tracking API client (bring-your-own per-tenant token).

Wraps httpx to call Callyzer's callHistory endpoint with a Bearer token. Surfaces
errors as `CallyzerError`, flagging `is_auth_error` (401/403 → token revoked/expired)
so the caller can flip the connection to `needs_reauth` and stop polling that tenant.
Respects Callyzer's documented rate limit (~1 request / 2s) with a pause between
pages and a bounded retry on HTTP 429. No global client exists in the app, so — like
services/meta_graph.py — each call constructs its own short-lived AsyncClient. The
token is never logged.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx

_BASE_URL = "https://api1.callyzer.co"
_CALL_HISTORY_PATH = "/admin/api/call/callHistory"
# Callyzer documents ~1 request / 2s; pause a hair over 2s between pages.
_RATE_LIMIT_SLEEP = 2.1
_MAX_429_RETRIES = 3
_PAGE_SIZE = 100
# Common envelope keys Callyzer might wrap the record list in (docs are a JS SPA the
# fetcher couldn't read, so we accept the documented shape or a bare list).
_LIST_KEYS = ("data", "result", "results", "callHistory", "call_history", "logs", "records")


class CallyzerError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status

    @property
    def is_auth_error(self) -> bool:
        """True when the token itself is bad (401/403) — the connection needs re-auth."""
        return self.http_status in (401, 403)


class CallyzerClient:
    def __init__(self, token: str) -> None:
        self._token = token or ""

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    @staticmethod
    def _extract_records(data: object) -> list[dict]:
        """Pull the call-record list out of whatever envelope Callyzer returns."""
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            for key in _LIST_KEYS:
                val = data.get(key)
                if isinstance(val, list):
                    return [r for r in val if isinstance(r, dict)]
        return []

    async def _post(self, body: dict) -> object:
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{_BASE_URL}{_CALL_HISTORY_PATH}", json=body, headers=self._headers
                    )
            except httpx.HTTPError as exc:  # network/timeout — transient
                raise CallyzerError(f"Callyzer request failed: {exc}") from exc
            if resp.status_code == 429 and attempt < _MAX_429_RETRIES:
                attempt += 1
                await asyncio.sleep(_RATE_LIMIT_SLEEP * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise CallyzerError(
                    f"Callyzer API error (HTTP {resp.status_code}): {resp.text[:200]}",
                    http_status=resp.status_code,
                )
            try:
                return resp.json()
            except ValueError as exc:
                raise CallyzerError(
                    f"Non-JSON Callyzer response (HTTP {resp.status_code}).",
                    http_status=resp.status_code,
                ) from exc

    async def probe(self) -> None:
        """Validation probe for the connect wizard — a tiny 1-record call-history request.
        Succeeds (even with 0 records) when the token is valid; raises CallyzerError with
        is_auth_error on a bad token."""
        await self._post({"recordFrom": "0", "pageSize": "1"})

    async def iter_call_history(
        self, *, start_date: str, end_date: str
    ) -> AsyncIterator[dict]:
        """Yield every call record in [start_date, end_date] (YYYY-MM-DD), paginating via
        recordFrom/pageSize and pausing between pages to honour the rate limit."""
        offset = 0
        while True:
            data = await self._post(
                {
                    "callStartDate": start_date,
                    "callEndDate": end_date,
                    "recordFrom": str(offset),
                    "pageSize": str(_PAGE_SIZE),
                }
            )
            records = self._extract_records(data)
            for rec in records:
                yield rec
            if len(records) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
            await asyncio.sleep(_RATE_LIMIT_SLEEP)
