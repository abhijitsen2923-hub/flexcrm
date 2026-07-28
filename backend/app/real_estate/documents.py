"""On-brand HTML documents for bookings (allotment letter, booking form, receipt).

Rendered from booking + unit + project + customer data. The same HTML is used for
the browser preview and for server-side PDF generation (see app/core/pdf.py). The
markup is deliberately engine-neutral — tables + <hr> instead of flex/float, and
"Rs." instead of the ₹ glyph — so it renders identically in WeasyPrint and in the
pure-Python xhtml2pdf fallback (which lacks flexbox and a Unicode font).
"""
from __future__ import annotations

from datetime import date
from html import escape

from app.models.customer import Customer
from app.real_estate.models import Booking, BookingInvoice, PaymentReceipt, Project, Tower, Unit


_MODE_LABELS = {
    "upi": "UPI",
    "neft": "NEFT / RTGS",
    "cheque": "Cheque",
    "cash": "Cash",
    "card": "Card",
    "other": "Other",
}

_TITLES = {
    "allotment_letter": "Allotment Letter",
    "booking_form": "Booking Form",
    "receipt": "Payment Receipt",
}

_INVOICE_STATUS_LABELS = {
    "draft": "Draft",
    "issued": "Issued",
    "paid": "Paid",
    "refunded": "Refunded",
    "void": "Void",
}


def _inr(value) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    s = str(int(round(n)))
    whole = s
    if len(s) > 3:  # Indian digit grouping, e.g. 12,34,567
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    # "Rs." (ASCII) rather than ₹ so it renders in every PDF engine's core font.
    return f"Rs. {whole}"


def _fmt_date(d) -> str:
    return d.isoformat() if isinstance(d, date) else "—"


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td class="k">{escape(label)}</td>'
        f'<td class="v">{escape(str(value))}</td></tr>'
    )


def _sign(left: str, right: str) -> str:
    """Signature block as a table (xhtml2pdf has no flexbox)."""
    return (
        '<br/><br/><br/>'
        '<table class="sign" width="100%"><tr>'
        f'<td width="45%">{escape(left)}</td>'
        '<td width="10%"></td>'
        f'<td width="45%">{escape(right)}</td>'
        '</tr></table>'
    )


_STYLE = """
  @page { size: a4; margin: 2cm; }
  body { font-family: Helvetica, Arial, sans-serif; color: #1f2937; }
  .builder { font-size: 20px; font-weight: bold; color: #0f172a; }
  .proj { color: #6b7280; font-size: 12px; }
  .rera { color: #6b7280; font-size: 10px; }
  h1 { font-size: 17px; margin: 10px 0 16px; }
  h3 { font-size: 12px; color: #6b7280; margin: 16px 0 6px; }
  p { font-size: 13px; }
  table.kv { width: 100%; }
  table.kv td { padding: 5px 6px; border-bottom: 1px solid #eef1f5; font-size: 13px; }
  td.k { color: #6b7280; width: 40%; }
  td.v { font-weight: bold; }
  .ref { color: #6b7280; font-size: 11px; }
  hr.rule { border: none; border-top: 3px solid #f59e0b; }
  table.sign td { border-top: 1px solid #9ca3af; padding-top: 6px; font-size: 12px; color: #374151; text-align: center; }
"""


def _shell(title: str, builder: str, proj_name: str, location: str,
           rera: str | None, ref_label: str, ref: str, body: str) -> str:
    rera_line = f'<div class="rera">RERA: {escape(rera)}</div>' if rera else ""
    proj_line = escape(proj_name) + ((" — " + escape(location)) if location else "")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
    <style>{_STYLE}</style></head><body>
      <table width="100%"><tr>
        <td>
          <div class="builder">{escape(builder)}</div>
          <div class="proj">{proj_line}</div>
          {rera_line}
        </td>
        <td align="right" valign="top"><span class="ref">{escape(ref_label)}: {escape(ref)}</span></td>
      </tr></table>
      <hr class="rule"/>
      <h1>{escape(title)}</h1>
      {body}
    </body></html>"""


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
    area = f"{unit.area} {unit.area_unit}" if unit else "—"  # super built-up (saleable)
    carpet = f"{unit.carpet_area} {unit.area_unit}" if unit and unit.carpet_area is not None else None
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
        _row("Super Built-up Area", area),
        *([_row("Carpet Area", carpet)] if carpet else []),
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
          {_sign("Applicant Signature", "For " + builder)}
        """
    elif doc_type == "receipt":
        body = f"""
          <p>Received with thanks from <strong>{escape(cust_name)}</strong> the sum of
          <strong>{escape(total)}</strong> towards booking of Unit
          <strong>{escape(unit_no)}</strong> in {escape(proj_name)}.</p>
          <h3>Unit Details</h3>
          {unit_table}
          <p>Registration Date: <strong>{escape(registration_date)}</strong></p>
          {_sign("Received By", "For " + builder)}
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
          {_sign("Applicant Signature", "Authorised Signatory")}
        """

    return _shell(title, builder, proj_name, location, rera, "Ref", ref, body), title


def render_installment_invoice(
    booking: Booking,
    unit: Unit | None,
    project: Project | None,
    tower: Tower | None,
    customer: Customer | None,
    invoice: BookingInvoice,
) -> tuple[str, str]:
    """Return (html, title) for a per-installment demand invoice."""
    title = "Invoice"

    builder = project.builder_name if project else "Builder"
    proj_name = project.name if project else "Project"
    location = f"{project.location}, {project.city}" if project else ""
    rera = project.rera_number if project and project.rera_number else None

    unit_no = unit.unit_number if unit else "—"
    tower_name = tower.name if tower else "—"
    cust_name = customer.contact_name if customer else "—"
    cust_email = customer.email if customer and customer.email else ""
    cust_phone = customer.phone if customer and customer.phone else ""

    amount = _inr(invoice.amount)
    status = _INVOICE_STATUS_LABELS.get(invoice.status, str(invoice.status))

    details = "<table class='kv'>" + "".join([
        _row("Invoice No.", invoice.invoice_number),
        _row("Invoice Date", _fmt_date(invoice.created_at.date() if invoice.created_at else None)),
        _row("Installment", invoice.installment_name),
        _row("Amount Due", amount),
        _row("Due Date", _fmt_date(invoice.due_date)),
        _row("Status", status),
        _row("Project", proj_name),
        _row("Tower / Unit", f"{tower_name} · {unit_no}"),
    ]) + "</table>"

    bill_to = "<table class='kv'>" + "".join([
        _row("Name", cust_name),
        *( [_row("Email", cust_email)] if cust_email else [] ),
        *( [_row("Phone", cust_phone)] if cust_phone else [] ),
    ]) + "</table>"

    body = f"""
      <p>This is a demand for the installment <strong>{escape(invoice.installment_name)}</strong>
      towards Unit <strong>{escape(unit_no)}</strong> in {escape(proj_name)}.
      Amount payable: <strong>{escape(amount)}</strong>.</p>
      <h3>Bill To</h3>
      {bill_to}
      <h3>Invoice Details</h3>
      {details}
      {_sign("Authorised Signatory", "For " + builder)}
    """

    return _shell(title, builder, proj_name, location, rera, "Invoice", invoice.invoice_number, body), title


def render_token_receipt(
    booking: Booking,
    unit: Unit | None,
    project: Project | None,
    tower: Tower | None,
    customer: Customer | None,
) -> tuple[str, str]:
    """Return (html, title) for a booking's token / booking-amount receipt."""
    title = "Token Receipt"

    builder = project.builder_name if project else "Builder"
    proj_name = project.name if project else "Project"
    location = f"{project.location}, {project.city}" if project else ""
    rera = project.rera_number if project and project.rera_number else None

    unit_no = unit.unit_number if unit else "—"
    tower_name = tower.name if tower else "—"
    cust_name = customer.contact_name if customer else "—"

    amount = _inr(booking.token_amount)
    mode = _MODE_LABELS.get(booking.token_mode, booking.token_mode or "—")
    ref_no = booking.token_reference or "—"
    receipt_no = str(booking.id)[:8].upper()

    details = "<table class='kv'>" + "".join([
        _row("Receipt No.", receipt_no),
        _row("Date", _fmt_date(booking.token_received_on)),
        _row("Token Amount", amount),
        _row("Payment Mode", mode),
        _row("Reference", ref_no),
        _row("Project", proj_name),
        _row("Tower / Unit", f"{tower_name} · {unit_no}"),
    ]) + "</table>"

    body = f"""
      <p>Received with thanks from <strong>{escape(cust_name)}</strong> the sum of
      <strong>{escape(amount)}</strong> as token / booking amount towards Unit
      <strong>{escape(unit_no)}</strong> in {escape(proj_name)}.</p>
      <h3>Token Details</h3>
      {details}
      {_sign("Received By", "For " + builder)}
    """

    return _shell(title, builder, proj_name, location, rera, "Receipt", receipt_no, body), title


def render_payment_receipt(
    booking: Booking,
    unit: Unit | None,
    project: Project | None,
    tower: Tower | None,
    customer: Customer | None,
    receipt: PaymentReceipt,
) -> tuple[str, str]:
    """Return (html, title) for a single payment receipt transaction."""
    title = "Payment Receipt"

    builder = project.builder_name if project else "Builder"
    proj_name = project.name if project else "Project"
    location = f"{project.location}, {project.city}" if project else ""
    rera = project.rera_number if project and project.rera_number else None

    unit_no = unit.unit_number if unit else "—"
    tower_name = tower.name if tower else "—"
    cust_name = customer.contact_name if customer else "—"

    amount = _inr(receipt.amount)
    mode = _MODE_LABELS.get(receipt.mode, receipt.mode)
    ref = receipt.reference or "—"
    receipt_no = str(receipt.id)[:8].upper()

    details = "<table class='kv'>" + "".join([
        _row("Receipt No.", receipt_no),
        _row("Date", _fmt_date(receipt.paid_on)),
        _row("Amount Received", amount),
        _row("Payment Mode", mode),
        _row("Reference", ref),
        _row("Project", proj_name),
        _row("Tower / Unit", f"{tower_name} · {unit_no}"),
    ]) + "</table>"

    body = f"""
      <p>Received with thanks from <strong>{escape(cust_name)}</strong> the sum of
      <strong>{escape(amount)}</strong> towards Unit <strong>{escape(unit_no)}</strong>
      in {escape(proj_name)}.</p>
      <h3>Payment Details</h3>
      {details}
      {('<p>' + escape(receipt.notes) + '</p>') if receipt.notes else ''}
      {_sign("Received By", "For " + builder)}
    """

    return _shell(title, builder, proj_name, location, rera, "Receipt", receipt_no, body), title
