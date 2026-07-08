"""Self-contained HTML documents for bookings (allotment letter, booking form,
receipt). Rendered from booking + unit + project + customer data and returned as
an HTML string the client previews in an iframe and prints (Save as PDF).

No PDF library / file storage is wired — HTML + browser print keeps it dependency
free while producing a real, on-brand document with the actual booking data.
"""
from __future__ import annotations

from datetime import date
from html import escape

from app.models.customer import Customer
from app.real_estate.models import Booking, Project, Tower, Unit


_TITLES = {
    "allotment_letter": "Allotment Letter",
    "booking_form": "Booking Form",
    "receipt": "Payment Receipt",
}


def _inr(value) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    # Indian digit grouping (e.g. 12,34,567).
    whole = f"{int(round(n)):,}"
    # Python's default grouping is western; convert to Indian for the tail.
    s = str(int(round(n)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return f"₹{whole}"


def _fmt_date(d) -> str:
    return d.isoformat() if isinstance(d, date) else "—"


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td class="k">{escape(label)}</td>'
        f'<td class="v">{escape(str(value))}</td></tr>'
    )


def render_booking_document(
    doc_type: str,
    booking: Booking,
    unit: Unit | None,
    project: Project | None,
    tower: Tower | None,
    customer: Customer | None,
) -> tuple[str, str]:
    """Return (html, title) for the requested booking document type."""
    title = _TITLES.get(doc_type, "Document")

    builder = project.builder_name if project else "Builder"
    proj_name = project.name if project else "Project"
    location = f"{project.location}, {project.city}" if project else ""
    rera = project.rera_number if project and project.rera_number else None

    unit_no = unit.unit_number if unit else "—"
    tower_name = tower.name if tower else "—"
    floor = unit.floor if unit else "—"
    area = f"{unit.area} {unit.area_unit}" if unit else "—"
    base_price = _inr(unit.base_price) if unit else "—"

    cust_name = customer.contact_name if customer else "—"
    cust_company = customer.company_name if customer and customer.company_name else ""
    cust_email = customer.email if customer and customer.email else ""
    cust_phone = customer.phone if customer and customer.phone else ""

    snap = booking.pricing_snapshot or {}
    total = _inr(snap["total"]) if isinstance(snap, dict) and snap.get("total") is not None else base_price
    registration_date = _fmt_date(booking.scheduled_date)
    ref = str(booking.id)[:8].upper()

    unit_table = "<table class='kv'>" + "".join([
        _row("Project", proj_name),
        _row("Tower", tower_name),
        _row("Unit No.", unit_no),
        _row("Floor", floor),
        _row("Carpet / Area", area),
        _row("Base Price", base_price),
    ]) + "</table>"

    customer_table = "<table class='kv'>" + "".join([
        _row("Name", cust_name),
        *( [_row("Company", cust_company)] if cust_company else [] ),
        *( [_row("Email", cust_email)] if cust_email else [] ),
        *( [_row("Phone", cust_phone)] if cust_phone else [] ),
    ]) + "</table>"

    if doc_type == "allotment_letter":
        body = f"""
          <p>Date: {escape(_fmt_date(date.today()))}</p>
          <p>Dear <strong>{escape(cust_name)}</strong>,</p>
          <p>We are pleased to confirm the allotment of the following unit in
          <strong>{escape(proj_name)}</strong>{(' , ' + escape(location)) if location else ''}, developed by
          <strong>{escape(builder)}</strong>.</p>
          <h3>Unit Details</h3>
          {unit_table}
          <h3>Allottee</h3>
          {customer_table}
          <p>Total Consideration: <strong>{escape(total)}</strong></p>
          <p>Registration Date: <strong>{escape(registration_date)}</strong></p>
          <p>This allotment is subject to the terms of the agreement to sale and
          applicable statutory approvals.</p>
          <div class="sign"><div>Applicant Signature</div><div>For {escape(builder)}</div></div>
        """
    elif doc_type == "receipt":
        body = f"""
          <p>Received with thanks from <strong>{escape(cust_name)}</strong> the sum of
          <strong>{escape(total)}</strong> towards booking of Unit
          <strong>{escape(unit_no)}</strong> in {escape(proj_name)}.</p>
          <h3>Unit Details</h3>
          {unit_table}
          <p>Registration Date: <strong>{escape(registration_date)}</strong></p>
          <div class="sign"><div>Received By</div><div>For {escape(builder)}</div></div>
        """
    else:  # booking_form
        body = f"""
          <h3>Applicant</h3>
          {customer_table}
          <h3>Unit</h3>
          {unit_table}
          <table class='kv'>
            {_row("Total Consideration", total)}
            {_row("Registration Date", registration_date)}
            {_row("Booking Ref", ref)}
          </table>
          <div class="sign"><div>Applicant Signature</div><div>Authorised Signatory</div></div>
        """

    rera_line = f"<div class='rera'>RERA: {escape(rera)}</div>" if rera else ""
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
    <style>
      * {{ box-sizing: border-box; }}
      body {{ font-family: Arial, Helvetica, sans-serif; color: #1f2937; margin: 0; padding: 32px; }}
      .doc {{ max-width: 720px; margin: 0 auto; }}
      .head {{ border-bottom: 3px solid #f59e0b; padding-bottom: 12px; margin-bottom: 20px; }}
      .builder {{ font-size: 22px; font-weight: 800; color: #0f172a; }}
      .proj {{ color: #6b7280; font-size: 13px; }}
      .rera {{ color: #6b7280; font-size: 11px; margin-top: 4px; }}
      h1 {{ font-size: 18px; text-transform: uppercase; letter-spacing: .05em; margin: 8px 0 20px; }}
      h3 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; margin: 20px 0 8px; }}
      p {{ font-size: 14px; line-height: 1.6; }}
      table.kv {{ width: 100%; border-collapse: collapse; }}
      table.kv td {{ padding: 6px 8px; border-bottom: 1px solid #eef1f5; font-size: 14px; }}
      td.k {{ color: #6b7280; width: 40%; }}
      td.v {{ font-weight: 600; }}
      .ref {{ float: right; color: #6b7280; font-size: 12px; }}
      .sign {{ display: flex; justify-content: space-between; margin-top: 56px; font-size: 13px; color: #374151; }}
      .sign div {{ border-top: 1px solid #9ca3af; padding-top: 6px; width: 40%; text-align: center; }}
      @media print {{ body {{ padding: 0; }} }}
    </style></head><body><div class="doc">
      <div class="head">
        <span class="ref">Ref: {escape(ref)}</span>
        <div class="builder">{escape(builder)}</div>
        <div class="proj">{escape(proj_name)}{(' — ' + escape(location)) if location else ''}</div>
        {rera_line}
      </div>
      <h1>{escape(title)}</h1>
      {body}
    </div></body></html>"""
    return html, title
