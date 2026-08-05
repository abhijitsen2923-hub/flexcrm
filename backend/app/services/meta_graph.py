"""Thin Meta Graph API client for Facebook/Instagram Lead Ads (bring-your-own-token).

Wraps httpx with a PINNED Graph version (settings.meta_graph_version). Used by both
the connect-wizard validation probe and the polling job. Surfaces Graph errors as
`MetaGraphError`, flagging `is_auth_error` (OAuthException code 190 → token revoked/
expired) so the caller can flip the connection to `needs_reauth` and stop polling
that org. No global client/retry layer exists in the app, so — like services/email.py
— each call constructs its own short-lived AsyncClient. Tokens are never logged.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings

_GRAPH_BASE = "https://graph.facebook.com"
# Auth errors — token invalid/expired/revoked. 190 is the umbrella OAuthException;
# 102 (session) / 10 & 200-299 (permission) are related but handled as generic.
_AUTH_ERROR_CODES = {190}


class MetaGraphError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        subcode: int | None = None,
        http_status: int | None = None,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.http_status = http_status
        self.error_type = error_type

    @property
    def is_auth_error(self) -> bool:
        """True when the token itself is bad (revoked/expired) — the connection
        needs re-auth, distinct from a missing Lead-Access grant or a transient error."""
        return self.code in _AUTH_ERROR_CODES


class MetaGraphClient:
    def __init__(self, access_token: str, *, version: str | None = None) -> None:
        self._token = access_token
        self._version = version or get_settings().meta_graph_version

    async def _request(self, url: str, params: dict | None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url, params=params or {})
        except httpx.HTTPError as exc:  # network/timeout — transient
            raise MetaGraphError(f"Graph request failed: {exc}") from exc
        try:
            data = resp.json()
        except ValueError:
            raise MetaGraphError(
                f"Non-JSON Graph response (HTTP {resp.status_code}).", http_status=resp.status_code
            )
        if resp.status_code >= 400 or (isinstance(data, dict) and "error" in data):
            err = data.get("error", {}) if isinstance(data, dict) else {}
            raise MetaGraphError(
                err.get("message") or f"Graph API error (HTTP {resp.status_code}).",
                code=err.get("code"),
                subcode=err.get("error_subcode"),
                http_status=resp.status_code,
                error_type=err.get("type"),
            )
        return data

    async def _paginate(self, path: str, params: dict) -> AsyncIterator[dict]:
        """Yield every item across pages. `paging.next` is a full URL with the token
        and cursor embedded, so we follow it directly."""
        url: str | None = f"{_GRAPH_BASE}/{self._version}/{path}"
        page_params: dict | None = {**params, "access_token": self._token}
        while url:
            data = await self._request(url, page_params)
            for item in data.get("data", []) or []:
                yield item
            url = (data.get("paging") or {}).get("next")
            page_params = None  # embedded in the next URL

    # --- public API --------------------------------------------------------

    async def probe_page(self, page_id: str) -> dict:
        """Validation probe for the connect wizard — resolves the page name (proves
        the token + Page id + basic access). Raises MetaGraphError on failure so the
        caller can classify (auth vs. permission vs. not-owned)."""
        return await self._request(
            f"{_GRAPH_BASE}/{self._version}/{page_id}",
            {"fields": "id,name", "access_token": self._token},
        )

    async def list_leadgen_forms(self, page_id: str) -> list[dict]:
        return [f async for f in self._paginate(f"{page_id}/leadgen_forms", {"fields": "id,name,status", "limit": 100})]

    async def iter_form_leads(self, form_id: str, *, since_unix: int | None = None) -> AsyncIterator[dict]:
        """Yield leadgen leads for a form, newest first, optionally created strictly
        AFTER `since_unix` (the stored per-form cursor). `platform` distinguishes
        Facebook vs Instagram; `id` is the leadgen_id (the idempotency anchor)."""
        params: dict = {
            "fields": "id,created_time,field_data,ad_id,ad_name,adset_name,"
            "campaign_id,campaign_name,form_id,form_name,platform,is_organic",
            "limit": 100,
        }
        if since_unix:
            params["filtering"] = json.dumps(
                [{"field": "time_created", "operator": "GREATER_THAN", "value": int(since_unix)}]
            )
        async for lead in self._paginate(f"{form_id}/leads", params):
            yield lead
