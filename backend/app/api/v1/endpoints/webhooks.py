"""Public inbound webhooks (no user session): Meta Lead Ads + 99acres.

Security is by payload/token, not by session. Meta: the leadgen GET handshake checks the verify
token; the leadgen POST checks `X-Hub-Signature-256`; deauthorize/data-deletion verify the
`signed_request`. 99acres: the URL path token IS the credential (its hash resolves the tenant via
the public lead_source_routes). All handlers use a fresh db session (like cron) because they switch
org scope per delivery. This whole prefix is exempt from IP rate limiting (see middleware) — the
callers authenticate themselves and behind Cloud Run share one client IP.
"""
import hashlib
import json
import secrets
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.tenancy import set_scope, set_tenant_schema
from app.database.session import db_manager
from app.services.lead_source_service import LeadSourceService
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


_MAX_META_BODY = 256 * 1024  # 256 KB — leadgen notifications are tiny; cap the unauth read.


@router.post("/meta")
async def meta_webhook_receive(request: Request):
    """Receive a leadgen notification. Verify the signature over the RAW body, then route +
    ingest. ALWAYS ACK 200 once the signature is valid — Meta retries non-200 aggressively,
    and the poll is our backstop for anything a single delivery fails to ingest."""
    # Rate-limit-exempt + unauthenticated until the signature check → cap the body
    # first so a crafted large payload can't force unbounded in-memory buffering.
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > _MAX_META_BODY:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Body too large.")
    raw = await request.body()
    if len(raw) > _MAX_META_BODY:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Body too large.")
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


# --- 99acres inbound leads (push) -----------------------------------------
# 99acres POSTs each lead to a per-account URL whose path token IS the credential. We resolve the
# token → tenant, DURABLY STORE the raw body, ACK 200, then map + ingest in the background. Unlike
# Meta there's no poll to re-fetch, so persist-first is what guarantees no paid-for lead is lost.


async def _process_99acres_delivery(delivery_id: UUID, organization_id: UUID, schema_name: str) -> None:
    """Background task (runs after the 200): map + ingest one stored delivery. Own session; the
    service handles its own commits + error isolation and never raises. A failure just leaves a
    replayable `failed` delivery for the reconcile cron."""
    async with db_manager.session_factory() as session:
        try:
            set_scope(session, organization_id)
            await set_tenant_schema(session, schema_name)
            await LeadSourceService(session).process_delivery(delivery_id, organization_id=organization_id)
        except Exception:  # noqa: BLE001 — never surface; cron reconciles
            logger.warning("99acres delivery processing failed for %s", delivery_id, exc_info=True)


# A lead payload is tiny; cap the body so an unauthenticated flood can't force multi-MB
# JSON parsing (this prefix is rate-limit-exempt and uvicorn imposes no default cap).
_MAX_99ACRES_BODY = 256 * 1024  # 256 KB


@router.post("/99acres/{token}")
async def receive_99acres(token: str, request: Request, background: BackgroundTasks):
    """Receive one 99acres lead. Resolve the URL token → tenant, persist the raw body, ACK 200,
    and process asynchronously. 404 = unknown/inactive token; 413 = body too large; 422 = malformed
    or missing Name/ContactNo (the delivery is still stored for audit).

    Ordering matters (DoS hardening): validate the URL token in a short-lived session and release
    its connection BEFORE reading the attacker-controlled body — so a bogus-token flood 404s without
    materialising/parsing a large body or holding a pooled connection across the read."""
    # 1) Authenticate on the URL token FIRST — cheap, indexed, own session released immediately.
    async with db_manager.session_factory() as auth_session:
        route = await LeadSourceService(auth_session).resolve_route(token)
        if route is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or inactive token.")
        organization_id = route.organization_id
        schema_name = route.schema_name
        token_hash = route.token_hash

    # 2) Now that the caller is authenticated, cap + read + parse the body.
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > _MAX_99ACRES_BODY:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Body too large.")
    raw = await request.body()
    if len(raw) > _MAX_99ACRES_BODY:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Body too large.")
    try:
        payload = json.loads(raw) if raw else None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Malformed JSON body.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Body must be a JSON object.")

    # 3) Persist first (own commit) so a later fault can't lose the lead, then validate.
    async with db_manager.session_factory() as session:
        svc = LeadSourceService(session)
        set_scope(session, organization_id)
        await set_tenant_schema(session, schema_name)
        delivery_id = await svc.persist_delivery(token_hash, payload)

        name = str(payload.get("Name") or payload.get("name") or "").strip()
        phone = str(payload.get("ContactNo") or payload.get("contact_no") or payload.get("phone") or "").strip()
        if not name or not phone:
            await svc.mark_delivery(
                delivery_id, status="ignored", error="Name and ContactNo are required."
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name and ContactNo are required.",
            )

    # ACK now; map + ingest after the response is sent.
    background.add_task(_process_99acres_delivery, delivery_id, organization_id, schema_name)
    return {"status": "accepted", "lead_id": payload.get("lead_id") or payload.get("leadId")}
