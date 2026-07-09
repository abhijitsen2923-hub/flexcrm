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
from app.jobs.registration_reminders import dispatch_registration_reminders

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
