"""Public inbound webhooks (no user session). Currently: Meta Lead Ads.

Meta delivers every tenant's events to these ONE-per-type callbacks. Security is by
payload, not by session: the leadgen GET handshake checks the verify token; the leadgen
POST checks the `X-Hub-Signature-256` HMAC over the raw body; the deauthorize +
data-deletion callbacks verify Meta's `signed_request` (HMAC with the app secret). Routing
to the right tenant is by `page_id` (leadgen) or Facebook `user_id` (deauth/data-deletion)
via the public MetaPageRoute registry. A fresh db session is used (like cron) because the
handlers switch org scope per page.
"""
import hashlib
import json
import secrets

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.session import db_manager
from app.services.meta_connection import purge_connections_for_user
from app.services.meta_oauth import parse_signed_request
from app.services.meta_webhook import MetaWebhookService, verify_signature

router = APIRouter()
logger = get_logger(__name__)


@router.get("/meta")
async def meta_webhook_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
):
    """Meta's subscription handshake: echo `hub.challenge` iff `hub.verify_token` matches
    our configured token. Inert (403) until META_WEBHOOK_VERIFY_TOKEN is set."""
    token = get_settings().meta_webhook_verify_token
    if (
        hub_mode == "subscribe"
        and token
        and hub_verify_token
        # Compare as bytes so a crafted non-ASCII token can't raise TypeError (500); it
        # still fails closed to the 403 below on any mismatch.
        and secrets.compare_digest(hub_verify_token.encode("utf-8"), token.encode("utf-8"))
    ):
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed.")


@router.post("/meta")
async def meta_webhook_receive(request: Request):
    """Receive a leadgen notification. Verify the signature over the RAW body, then route +
    ingest. ALWAYS ACK 200 once the signature is valid — Meta retries non-200 aggressively,
    and the poll is our backstop for anything a single delivery fails to ingest."""
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature.")
    try:
        payload = json.loads(raw)
    except ValueError:
        # Signed but non-JSON — nothing to do; ACK so Meta stops retrying.
        return {"status": "ignored"}
    async with db_manager.session_factory() as session:
        try:
            await MetaWebhookService(session).process_payload(payload)
        except Exception:  # noqa: BLE001 — never 500 to Meta; the poll backfills
            logger.warning("meta webhook processing failed", exc_info=True)
    return {"status": "ok"}


# --- App lifecycle callbacks (deauthorize + data deletion) ----------------
# Meta POSTs a `signed_request` (HMAC-signed with the app secret) carrying the user_id.
# Both required for App Review. They route by the granting user via the public route table.


@router.post("/meta/deauthorize")
async def meta_deauthorize(signed_request: str = Form(...)):
    """Meta calls this when a user removes FlexCRM from their Facebook account. Verify the
    signed_request, then disconnect every Page that user connected (their tokens are now
    dead). ACK 200 regardless — a forged/invalid request is a no-op."""
    data = parse_signed_request(signed_request)
    if not data or not data.get("user_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signed_request.")
    async with db_manager.session_factory() as session:
        try:
            await purge_connections_for_user(session, str(data["user_id"]))
        except Exception:  # noqa: BLE001 — never 500 to Meta
            logger.warning("meta deauthorize purge failed", exc_info=True)
    return {"status": "ok"}


@router.post("/meta/data-deletion")
async def meta_data_deletion(request: Request, signed_request: str = Form(...)):
    """Meta's data-deletion callback. Verify, delete the user's connection data (tokens +
    connections), and return the {url, confirmation_code} JSON Meta requires. Deletion is
    synchronous, so it's already done by the time Meta reads the response. Ingested leads are
    the business's own records (not the FB user's personal data) and are NOT deleted."""
    data = parse_signed_request(signed_request)
    if not data or not data.get("user_id"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signed_request.")
    user_id = str(data["user_id"])
    async with db_manager.session_factory() as session:
        try:
            await purge_connections_for_user(session, user_id)
        except Exception:  # noqa: BLE001 — never 500 to Meta
            logger.warning("meta data-deletion purge failed", exc_info=True)
    # A non-secret, deterministic tracking code (no PII, no token). The status URL below
    # simply confirms completion — the deletion already happened above.
    code = hashlib.sha256(f"{user_id}:meta-data-deletion".encode()).hexdigest()[:16]
    # `code` is url-safe hex; str() handles url_for returning either a URL object or a str.
    status_url = str(request.url_for("meta_data_deletion_status"))
    return {"url": f"{status_url}?code={code}", "confirmation_code": code}


@router.get("/meta/data-deletion/status")
async def meta_data_deletion_status(code: str | None = None):
    """Public status page for a data-deletion request (the URL returned to Meta above).
    The purge is synchronous, so by the time this is visited the data is already gone."""
    return PlainTextResponse(
        "Your FlexCRM Meta connection data has been deleted. "
        f"Confirmation code: {code or 'n/a'}"
    )
