"""Machine-triggered cron endpoints (no user session).

Protected by a shared secret sent in the ``X-Cron-Key`` header and compared
constant-time to ``settings.cron_secret`` — so an external scheduler (e.g. the
Cloudflare Worker cron) can fire them without a login. A dedicated header (not
``Authorization: Bearer``) keeps this off the JWT path entirely. The endpoints
are inert (403) until ``CRON_SECRET`` is configured, so they're safe by default.
"""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.database.session import db_manager
from app.jobs.archive import dispatch_archival
from app.jobs.customer_health import dispatch_customer_health
from app.jobs.followup_reminders import dispatch_followup_reminders
from app.jobs.lead_source_reconcile import dispatch_lead_source_reconcile
from app.jobs.meta_lead_sync import dispatch_meta_lead_sync
from app.jobs.meta_token_refresh import dispatch_meta_token_refresh
from app.jobs.registration_reminders import dispatch_registration_reminders
from app.jobs.scorecard_compute import dispatch_scorecard_compute

router = APIRouter()


def require_cron_secret(x_cron_key: str | None = Header(default=None, alias="X-Cron-Key")) -> None:
    secret = get_settings().cron_secret
    if not secret or not x_cron_key or not secrets.compare_digest(x_cron_key, secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing cron key.")


@router.post("/registration-reminders")
async def trigger_registration_reminders(_: None = Depends(require_cron_secret)):
    """Cross-org: notify owners of imminent registrations. Uses a fresh session
    (not the tenant-scoped request session) since dispatch switches org scope
    itself and commits per org."""
    async with db_manager.session_factory() as session:
        counts = await dispatch_registration_reminders(session)
    return counts


@router.post("/followup-reminders")
async def trigger_followup_reminders(_: None = Depends(require_cron_secret)):
    """Cross-org: email + notify each executive their due/overdue follow-ups
    (based on each lead's latest next_action_date). Fresh session — dispatch
    switches org scope itself and commits per org."""
    async with db_manager.session_factory() as session:
        counts = await dispatch_followup_reminders(session)
    return counts


@router.post("/meta-lead-sync")
async def trigger_meta_lead_sync(_: None = Depends(require_cron_secret)):
    """Cross-org: poll every connected org's Meta (Facebook/Instagram) Lead Ads and
    ingest new leads. Fresh session — dispatch switches org scope itself and commits
    per org. Meant to run every 5-15 min."""
    async with db_manager.session_factory() as session:
        counts = await dispatch_meta_lead_sync(session)
    return counts


@router.post("/meta-token-refresh")
async def trigger_meta_token_refresh(_: None = Depends(require_cron_secret)):
    """Cross-org: re-extend OAuth Meta tokens nearing expiry and flip revoked connections
    to needs_reauth. Fresh session — dispatch switches org scope itself and commits per
    connection. Meant to run daily."""
    async with db_manager.session_factory() as session:
        counts = await dispatch_meta_token_refresh(session)
    return counts


@router.post("/lead-source-reconcile")
async def trigger_lead_source_reconcile(_: None = Depends(require_cron_secret)):
    """Cross-org: replay any 99acres deliveries the persist-then-ACK background step didn't finish
    (status received/failed). Idempotent — dedupes on external_id. Fresh session; dispatch switches
    org scope itself and commits per delivery. Backstop for the push-only ingest; runs 2x/day."""
    async with db_manager.session_factory() as session:
        counts = await dispatch_lead_source_reconcile(session)
    return counts


@router.post("/customer-health")
async def trigger_customer_health(_: None = Depends(require_cron_secret)):
    """Cross-org: re-evaluate every customer's lifecycle stage and LTV. Fresh session —
    dispatch switches org scope itself and commits per org. Meant to run nightly."""
    async with db_manager.session_factory() as session:
        counts = await dispatch_customer_health(session)
    return counts


@router.post("/scorecard-compute")
async def trigger_scorecard_compute(_: None = Depends(require_cron_secret)):
    """Cross-org: write today's HR performance snapshot per active sales user.
    Idempotent per (user, date). Fresh session — dispatch switches org scope itself
    and commits per org. Meant to run nightly."""
    async with db_manager.session_factory() as session:
        counts = await dispatch_scorecard_compute(session)
    return counts


@router.post("/archive")
async def trigger_archive(_: None = Depends(require_cron_secret)):
    """Cross-org: hard-delete rows soft-deleted beyond ARCHIVAL_RETENTION_DAYS.
    Fresh session — dispatch switches org scope itself, commits per org, then purges
    the shared public `users` table once with routing cleared. Meant to run nightly."""
    async with db_manager.session_factory() as session:
        report = await dispatch_archival(session)
    return {
        "cutoff": report.cutoff.isoformat(),
        "orgs": report.orgs,
        "deleted": report.deleted,
        "skipped_customers": report.skipped_customers,
    }
