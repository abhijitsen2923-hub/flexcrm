"""Public inbound webhooks (no user session). Currently: Meta Lead Ads leadgen.

Meta delivers every tenant's new leads to this ONE callback. Security is by payload,
not by session: the GET handshake checks the verify token; the POST checks the
`X-Hub-Signature-256` HMAC over the raw body (see services/meta_webhook). Routing to
the right tenant is by `page_id` via the public MetaPageRoute registry. A fresh
db session is used (like cron) because the handler switches org scope per page.
"""
import json
import secrets

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.session import db_manager
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
