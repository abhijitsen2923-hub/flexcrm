"""OAuth "Connect Facebook" — FlexCRM's OWN app mints tenant connections.

Flow: tenant clicks Connect → we redirect the browser to Meta's OAuth dialog →
Meta redirects back with a `code` → we exchange it for a long-lived user token and
list the user's Pages → the admin picks which Page(s) to connect.

State binding (CSRF + tenancy): the `state` param is an HMAC-signed, short-lived
token carrying the initiating org_id, so the PUBLIC callback can trust which tenant
it belongs to and an attacker can't graft a connection onto another workspace.

App-Review note: this path needs FlexCRM's app to have Advanced Access (Meta review).
In Development mode it works for app-role users. The bring-your-own-token flow needs
neither. This module is stateless (no DB); the connection write lives in
services/meta_connection.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.services.meta_graph import MetaGraphClient, MetaGraphError

# Scopes FlexCRM requests to read a Page's lead-gen leads (+ subscribe its webhook).
_OAUTH_SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "leads_retrieval",
    "pages_manage_metadata",  # to subscribe the page to the app webhook (Phase 2)
    "business_management",
)
_STATE_TTL_SECONDS = 600  # the OAuth round-trip must complete within 10 minutes
_DIALOG = "https://www.facebook.com/{version}/dialog/oauth"


def is_oauth_configured() -> bool:
    """True only when FlexCRM's own Meta app credentials are set (env/secrets)."""
    s = get_settings()
    return bool(s.meta_app_id and s.meta_app_secret and s.meta_oauth_redirect_uri)


class MetaOAuthService:
    """Stateless helper — signs/verifies the state and talks to Meta's OAuth."""

    def __init__(self) -> None:
        self._s = get_settings()

    # --- state (CSRF + tenant binding) -------------------------------------

    def _sign(self, body: str) -> str:
        # HMAC key = the app secret (present whenever OAuth is configured).
        return hmac.new(
            (self._s.meta_app_secret or "").encode(), body.encode(), hashlib.sha256
        ).hexdigest()

    def build_state(self, org_id: UUID) -> str:
        payload = {
            "org": str(org_id),
            "n": secrets.token_urlsafe(8),
            "exp": int(time.time()) + _STATE_TTL_SECONDS,
        }
        body = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
        return f"{body}.{self._sign(body)}"

    def verify_state(self, state: str) -> UUID:
        """Return the org_id the OAuth flow was started for, or raise ValidationError."""
        try:
            body, sig = state.rsplit(".", 1)
        except ValueError as exc:
            raise ValidationError("Invalid OAuth state.") from exc
        if not hmac.compare_digest(sig, self._sign(body)):
            raise ValidationError("OAuth state signature mismatch.")
        try:
            payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        except Exception as exc:  # noqa: BLE001 — malformed/base64 error → reject
            raise ValidationError("Malformed OAuth state.") from exc
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValidationError("OAuth state expired — please start connecting again.")
        return UUID(payload["org"])

    # --- authorize URL -----------------------------------------------------

    def build_authorize_url(self, org_id: UUID) -> str:
        params = {
            "client_id": self._s.meta_app_id,
            "redirect_uri": self._s.meta_oauth_redirect_uri,
            "state": self.build_state(org_id),
            "scope": ",".join(_OAUTH_SCOPES),
            "response_type": "code",
        }
        return f"{_DIALOG.format(version=self._s.meta_graph_version)}?{urlencode(params)}"

    # --- code exchange -----------------------------------------------------

    async def exchange_code_for_user_token(self, code: str) -> tuple[str, int | None]:
        """`code` → short-lived user token → long-lived user token.
        Returns (long_lived_token, expires_in_seconds | None)."""
        client = MetaGraphClient()  # no token yet
        short = await client.exchange_code(
            code,
            app_id=self._s.meta_app_id,
            app_secret=self._s.meta_app_secret,
            redirect_uri=self._s.meta_oauth_redirect_uri,
        )
        short_token = short.get("access_token")
        if not short_token:
            raise ValidationError("Meta did not return an access token.")
        long = await client.long_lived_user_token(
            short_token, app_id=self._s.meta_app_id, app_secret=self._s.meta_app_secret
        )
        return (long.get("access_token") or short_token), long.get("expires_in")

    async def list_pages(self, user_token: str) -> list[dict]:
        """The Pages this user manages, each with its own access_token + IG link."""
        return await MetaGraphClient(user_token).list_pages()

    async def refresh_user_token(self, current_long_token: str) -> tuple[str, int | None]:
        """Re-extend a long-lived user token before it expires. fb_exchange_token accepts a
        long-lived token and returns a fresh ~60-day one. Returns (token, expires_in|None).
        Raises MetaGraphError (auth) if the user revoked access — the caller flips to reauth."""
        data = await MetaGraphClient().long_lived_user_token(
            current_long_token, app_id=self._s.meta_app_id, app_secret=self._s.meta_app_secret
        )
        token = data.get("access_token")
        if not token:
            raise ValidationError("Meta did not return a refreshed token.")
        return token, data.get("expires_in")

    async def get_user_id(self, user_token: str) -> str | None:
        """The Facebook user id behind a user token (for deauth/data-deletion routing).
        Best-effort — returns None on any Graph failure rather than blocking the connect."""
        try:
            me = await MetaGraphClient(user_token).get_me()
        except MetaGraphError:
            return None
        uid = me.get("id")
        return str(uid) if uid else None


def parse_signed_request(signed_request: str) -> dict | None:
    """Verify + decode a Meta `signed_request` (the deauthorize + data-deletion callbacks).

    Format: `<base64url signature>.<base64url json payload>`, where the signature is
    HMAC-SHA256(app_secret, <payload base64url string>). Returns the payload dict ONLY on a
    valid signature; returns None (never raises) on a missing secret, malformed input, or a
    signature mismatch — so a forged callback is silently ignored, not acted on."""
    secret = get_settings().meta_app_secret
    if not secret or not signed_request or "." not in signed_request:
        return None
    try:
        sig_b64, payload_b64 = signed_request.split(".", 1)
        expected = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
        got = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
        if not hmac.compare_digest(got, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
    except Exception:  # noqa: BLE001 — any decode/parse failure → treat as unverified
        return None
    return payload if isinstance(payload, dict) else None
