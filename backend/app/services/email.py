"""Transactional email via the Resend HTTPS API.

Every send is best-effort: if `RESEND_API_KEY` is unset the send is a logged
no-op, and any transport error is swallowed + logged (a failed email must never
break the request that triggered it). All bodies are branded HTML built from a
single inline-CSS shell (email clients need inline styles, no external assets).
"""
from collections.abc import Sequence
from html import escape

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_BRAND = "FlexCRM"


def _shell(*, heading: str, intro: str, rows: Sequence[tuple[str, str]] | None = None,
           cta_label: str | None = None, cta_url: str | None = None,
           outro: str | None = None) -> str:
    """Render a branded, email-client-safe HTML body (inline styles, tables)."""
    rows_html = ""
    if rows:
        cells = "".join(
            f'<tr>'
            f'<td style="padding:6px 12px;color:#64748b;font-size:13px;white-space:nowrap;">{escape(str(label))}</td>'
            f'<td style="padding:6px 12px;color:#0f172a;font-size:14px;font-weight:600;">{escape(str(value))}</td>'
            f'</tr>'
            for label, value in rows
        )
        rows_html = (
            '<table role="presentation" cellpadding="0" cellspacing="0" '
            'style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:8px;margin:16px 0;">'
            f'{cells}</table>'
        )
    cta_html = ""
    if cta_label and cta_url:
        cta_html = (
            f'<a href="{escape(cta_url)}" '
            'style="display:inline-block;margin:8px 0 4px;padding:11px 20px;background:#2563eb;color:#ffffff;'
            'text-decoration:none;border-radius:8px;font-size:14px;font-weight:600;">'
            f'{escape(cta_label)}</a>'
        )
    outro_html = f'<p style="color:#475569;font-size:14px;line-height:1.6;margin:16px 0 0;">{escape(outro)}</p>' if outro else ""
    return (
        '<div style="background:#eef2f7;padding:24px 0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">'
        '<div style="background:#0f172a;padding:18px 24px;">'
        f'<span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:.02em;">{_BRAND}</span>'
        '</div>'
        '<div style="padding:24px;">'
        f'<h1 style="color:#0f172a;font-size:19px;margin:0 0 12px;">{escape(heading)}</h1>'
        f'<p style="color:#475569;font-size:14px;line-height:1.6;margin:0;">{escape(intro)}</p>'
        f'{rows_html}{cta_html}{outro_html}'
        '</div>'
        '<div style="padding:14px 24px;border-top:1px solid #e2e8f0;">'
        f'<span style="color:#94a3b8;font-size:12px;">Sent by {_BRAND}. This is an automated message.</span>'
        '</div></div></div>'
    )


class EmailService:
    async def send_email(
        self,
        *,
        recipient: str | Sequence[str],
        subject: str,
        html: str,
        text: str | None = None,
    ) -> None:
        settings = get_settings()
        if not settings.resend_api_key:
            logger.info("Email not configured (RESEND_API_KEY unset). Skipping '%s' to %s.", subject, recipient)
            return
        to = [recipient] if isinstance(recipient, str) else list(recipient)
        to = [addr for addr in to if addr]
        if not to:
            return
        payload: dict = {"from": settings.email_from, "to": to, "subject": subject, "html": html}
        if text:
            payload["text"] = text
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    _RESEND_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                )
            if resp.status_code >= 400:
                logger.warning("Resend send failed (%s) to %s: %s", resp.status_code, to, resp.text[:300])
        except Exception as exc:  # best-effort: never break the caller
            logger.warning("Resend send error to %s: %s", to, exc)

    def _url(self, path: str) -> str:
        base = get_settings().app_base_url.rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    # --- account / assignment (existing signatures — kept) -----------------
    async def send_welcome_email(self, recipient: str, first_name: str) -> None:
        html = _shell(
            heading=f"Welcome to {_BRAND}, {first_name}!",
            intro="Your account is ready. Sign in to start managing your pipeline, customers and deals.",
            cta_label="Open FlexCRM", cta_url=self._url("/login"),
        )
        await self.send_email(recipient=recipient, subject=f"Welcome to {_BRAND}", html=html,
                              text=f"Welcome to {_BRAND}, {first_name}. Your account is ready: {self._url('/login')}")

    async def send_assignment_email(self, recipient: str, assignee_name: str, resource_label: str) -> None:
        html = _shell(
            heading="You have a new assignment",
            intro=f"Hi {assignee_name}, {resource_label} has been assigned to you. Open FlexCRM to review it.",
            cta_label="Review in FlexCRM", cta_url=self._url("/leads"),
        )
        await self.send_email(recipient=recipient, subject=f"New assignment: {resource_label}", html=html,
                              text=f"{assignee_name}, {resource_label} was assigned to you. {self._url('/leads')}")

    # --- real-estate lifecycle --------------------------------------------
    async def send_registration_reminder(self, recipient: str, *, unit_label: str, register_on: str, project: str | None = None) -> None:
        rows = [("Unit", unit_label), ("Registration due", register_on)]
        if project:
            rows.insert(0, ("Project", project))
        html = _shell(
            heading="Registration due soon",
            intro="A confirmed booking is approaching its registration date and the unit is still marked Booked.",
            rows=rows, cta_label="Open registration tracker", cta_url=self._url("/trackers/registration"),
        )
        await self.send_email(recipient=recipient, subject=f"Registration due {register_on} — {unit_label}", html=html)

    async def send_booking_confirmation(self, recipient: str, *, customer_name: str, unit_label: str,
                                        project: str | None, amount: str, register_on: str | None) -> None:
        rows = [("Unit", unit_label), ("Total consideration", amount)]
        if project:
            rows.insert(0, ("Project", project))
        if register_on:
            rows.append(("Registration date", register_on))
        html = _shell(
            heading="Your booking is confirmed",
            intro=f"Hi {customer_name}, your unit booking is confirmed. Here are the details.",
            rows=rows, outro="Our team will be in touch about the next steps.",
        )
        await self.send_email(recipient=recipient, subject=f"Booking confirmed — {unit_label}", html=html)

    async def send_payment_receipt(self, recipient: str, *, customer_name: str, amount: str,
                                   mode: str, paid_on: str, unit_label: str, reference: str | None = None) -> None:
        rows = [("Amount", amount), ("Mode", mode.upper()), ("Date", paid_on), ("Unit", unit_label)]
        if reference:
            rows.append(("Reference", reference))
        html = _shell(
            heading="Payment received",
            intro=f"Hi {customer_name}, we've recorded your payment. Thank you.",
            rows=rows,
        )
        await self.send_email(recipient=recipient, subject=f"Payment received — {amount}", html=html)

    async def send_refund_notice(self, recipient: str, *, customer_name: str, refund_amount: str,
                                 deduction: str | None, unit_label: str) -> None:
        rows = [("Refund amount", refund_amount), ("Unit", unit_label)]
        if deduction:
            rows.append(("Deduction withheld", deduction))
        html = _shell(
            heading="Refund processed",
            intro=f"Hi {customer_name}, your booking has been cancelled and a refund processed.",
            rows=rows, outro="Please allow a few working days for the amount to reflect.",
        )
        await self.send_email(recipient=recipient, subject=f"Refund processed — {refund_amount}", html=html)

    async def send_followup_digest(self, recipient: str, *, rep_name: str, items: Sequence[dict]) -> None:
        """Daily digest of a rep's due/overdue follow-ups. `items`: dicts with
        keys lead (number), name, due (formatted), note."""
        rows: list[tuple[str, str]] = []
        for it in items:
            label = f"#{it.get('lead', '')} {it.get('name', '')}".strip()
            note = (it.get("note") or "").strip()
            value = f"due {it.get('due', '')}" + (f" — {note}" if note else "")
            rows.append((label, value))
        n = len(items)
        html = _shell(
            heading=f"You have {n} follow-up{'s' if n != 1 else ''} due",
            intro=f"Hi {rep_name}, these leads need a follow-up today. Log the call and set the next action so none slip.",
            rows=rows, cta_label="Open my leads", cta_url=self._url("/leads"),
        )
        await self.send_email(
            recipient=recipient,
            subject=f"{n} follow-up{'s' if n != 1 else ''} due today",
            html=html,
        )

    # --- alerts (staff) ----------------------------------------------------
    async def send_partner_referral_alert(self, recipients: Sequence[str], *, partner: str,
                                          contact_name: str, requirement: str | None) -> None:
        rows = [("Referred by", partner), ("Prospect", contact_name)]
        if requirement:
            rows.append(("Requirement", requirement))
        html = _shell(
            heading="New channel-partner referral",
            intro=f"{partner} just submitted a new referral. Assign an owner to follow up.",
            rows=rows, cta_label="Open leads", cta_url=self._url("/leads"),
        )
        await self.send_email(recipient=list(recipients), subject=f"New referral from {partner}", html=html)

    async def send_site_visit_notification(self, recipient: str, *, rep_name: str, project: str,
                                          scheduled_at: str, lead_name: str | None) -> None:
        rows = [("Project", project), ("When", scheduled_at)]
        if lead_name:
            rows.append(("Lead", lead_name))
        html = _shell(
            heading="Site visit scheduled",
            intro=f"Hi {rep_name}, a site visit has been scheduled for you.",
            rows=rows, cta_label="Open site visits", cta_url=self._url("/site-visits"),
        )
        await self.send_email(recipient=recipient, subject=f"Site visit — {project} — {scheduled_at}", html=html)
