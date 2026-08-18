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
    def __init__(self, access_token: str | None = None, *, version: str | None = None) -> None:
        # Optional so app-level OAuth calls (code exchange) can use a token-less client.
        self._token = access_token or ""
        self._version = version or get_settings().meta_graph_version

    @staticmethod
    def _parse(resp: httpx.Response) -> dict:
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

    async def _request(self, url: str, params: dict | None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url, params=params or {})
        except httpx.HTTPError as exc:  # network/timeout — transient
            raise MetaGraphError(f"Graph request failed: {exc}") from exc
        return self._parse(resp)

    async def _post(self, url: str, params: dict | None) -> dict:
        """POST with params in the query string (Meta's write endpoints, e.g. app
        subscription). Same error surfacing as _request."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, params=params or {})
        except httpx.HTTPError as exc:  # network/timeout — transient
            raise MetaGraphError(f"Graph request failed: {exc}") from exc
        return self._parse(resp)

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

    # --- OAuth "Connect Facebook" (Phase 1) --------------------------------
    # Meta's OAuth token endpoints are GET, so they reuse _request. These take the
    # app credentials per-call (no token on the client yet for the code exchange).

    async def exchange_code(self, code: str, *, app_id: str, app_secret: str, redirect_uri: str) -> dict:
        """Exchange an OAuth authorization code for a (short-lived) user access token.
        Returns Meta's {access_token, token_type, expires_in?}."""
        return await self._request(
            f"{_GRAPH_BASE}/{self._version}/oauth/access_token",
            {
                "client_id": app_id,
                "client_secret": app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )

    async def long_lived_user_token(self, short_token: str, *, app_id: str, app_secret: str) -> dict:
        """Exchange a short-lived user token for a long-lived (~60-day) one.
        Returns {access_token, token_type, expires_in}."""
        return await self._request(
            f"{_GRAPH_BASE}/{self._version}/oauth/access_token",
            {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
        )

    async def get_me(self) -> dict:
        """The authenticated user's id/name (uses this client's USER token). Used to
        attribute a connection to the granting Facebook user for the deauthorize +
        data-deletion callbacks."""
        return await self._request(
            f"{_GRAPH_BASE}/{self._version}/me",
            {"fields": "id,name", "access_token": self._token},
        )

    async def list_pages(self) -> list[dict]:
        """Pages the current USER manages (uses this client's user token). Each item
        carries the Page's OWN access_token + linked Instagram business account."""
        return [
            page
            async for page in self._paginate(
                "me/accounts",
                {"fields": "id,name,access_token,instagram_business_account,tasks", "limit": 100},
            )
        ]

    async def get_lead(self, leadgen_id: str) -> dict:
        """Fetch a single leadgen lead by id — the webhook ingest path (Phase 2)."""
        return await self._request(
            f"{_GRAPH_BASE}/{self._version}/{leadgen_id}",
            {
                "fields": "id,created_time,field_data,ad_id,ad_name,adset_name,"
                "campaign_id,campaign_name,form_id,form_name,platform,is_organic",
                "access_token": self._token,
            },
        )

    async def subscribe_leadgen(self, page_id: str) -> dict:
        """Subscribe THIS app to the Page's `leadgen` webhooks (uses this client's PAGE
        token, which must carry pages_manage_metadata). After this, Meta pushes each new
        lead to the app's configured callback URL. Returns Meta's {"success": true}."""
        return await self._post(
            f"{_GRAPH_BASE}/{self._version}/{page_id}/subscribed_apps",
            {"subscribed_fields": "leadgen", "access_token": self._token},
        )
