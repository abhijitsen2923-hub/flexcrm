"""On-brand HTML/PDF documents for finance — demand letter, payment receipt,
expense voucher. Engine-neutral markup (tables + <hr>, "Rs." not the ₹ glyph)
so it renders in both WeasyPrint and the xhtml2pdf fallback (see app/core/pdf.py).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from html import escape


def _inr(value) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    s = str(int(round(n)))
    whole = s
    if len(s) > 3:  # Indian digit grouping
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return f"Rs. {whole}"


def _fmt_date(d) -> str:
    return d.isoformat() if isinstance(d, date) else "—"


def _row(label: str, value: str) -> str:
    return f'<tr><td class="k">{escape(label)}</td><td class="v">{escape(str(value))}</td></tr>'


def _sign(left: str, right: str = "") -> str:
    return (
        '<br/><br/><br/>'
        '<table class="sign" width="100%"><tr>'
        f'<td width="45%">{escape(left)}</td><td width="10%"></td>'
        f'<td width="45%">{escape(right)}</td></tr></table>'
    )


_STYLE = """
  @page { size: a4; margin: 2cm; }
  body { font-family: Helvetica, Arial, sans-serif; color: #1f2937; }
  .org { font-size: 20px; font-weight: bold; color: #0f172a; }
  h1 { font-size: 17px; margin: 10px 0 16px; }
  p { font-size: 13px; }
  table.kv { width: 100%; }
  table.kv td { padding: 5px 6px; border-bottom: 1px solid #eef1f5; font-size: 13px; }
  td.k { color: #6b7280; width: 45%; }
  td.v { font-weight: bold; }
  .ref { color: #6b7280; font-size: 11px; }
  hr.rule { border: none; border-top: 3px solid #f59e0b; }
  table.sign td { border-top: 1px solid #9ca3af; padding-top: 6px; font-size: 12px; color: #374151; text-align: center; }
"""


def _shell(title: str, org_name: str, ref_label: str, ref: str, body: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
    <style>{_STYLE}</style></head><body>
      <table width="100%"><tr>
        <td><div class="org">{escape(org_name)}</div></td>
        <td align="right" valign="top"><span class="ref">{escape(ref_label)}: {escape(ref)}</span></td>
      </tr></table>
      <hr class="rule"/>
      <h1>{escape(title)}</h1>
      {body}
    </body></html>"""


def render_demand_letter(*, demand, contract, customer_name: str, org_name: str) -> str:
    outstanding = Decimal(demand.amount or 0) - Decimal(demand.amount_received or 0)
    rows = (
        _row("Customer", customer_name)
        + _row("Contract", contract.title)
        + _row("Contract value", _inr(contract.contract_value))
        + (_row("Description", demand.description) if demand.description else "")
        + _row("Demand amount", _inr(demand.amount))
        + _row("Due date", _fmt_date(demand.due_date))
        + _row("Received so far", _inr(demand.amount_received))
        + _row("Amount now due", _inr(outstanding))
    )
    body = (
        "<p>Please find below the payment demand raised against your contract. "
        "Kindly arrange payment of the amount now due on or before the due date.</p>"
        f'<table class="kv">{rows}</table>'
        + _sign("Authorised Signatory")
    )
    return _shell("Demand Letter", org_name, "Demand #", demand.demand_number, body)


def render_demand_receipt(*, receipt, demand, contract, customer_name: str, org_name: str) -> str:
    rows = (
        _row("Customer", customer_name)
        + _row("Contract", contract.title)
        + _row("Against demand", demand.demand_number)
        + _row("Amount received", _inr(receipt.amount))
        + _row("Received on", _fmt_date(receipt.received_on))
        + (_row("Mode", receipt.method) if receipt.method else "")
        + (_row("Reference", receipt.txn_ref) if receipt.txn_ref else "")
    )
    body = (
        "<p>We acknowledge with thanks receipt of the following payment.</p>"
        f'<table class="kv">{rows}</table>'
        + _sign("Authorised Signatory")
    )
    return _shell("Payment Receipt", org_name, "Receipt #", receipt.receipt_number, body)


def render_expense_voucher(*, expense, category_name: str, vendor_name: str | None, org_name: str) -> str:
    gst = Decimal(expense.cgst_amount or 0) + Decimal(expense.sgst_amount or 0) + Decimal(expense.igst_amount or 0)
    rows = (
        _row("Title", expense.title)
        + _row("Category", category_name)
        + (_row("Vendor", vendor_name) if vendor_name else "")
        + _row("Date", _fmt_date(expense.expense_date))
        + _row("Status", str(expense.status.value if hasattr(expense.status, "value") else expense.status).title())
        + _row("Taxable amount", _inr(expense.taxable_amount))
        + (_row("GST", _inr(gst)) if gst else "")
        + (_row("TDS", _inr(expense.tds_amount)) if Decimal(expense.tds_amount or 0) else "")
        + _row("Total", _inr(expense.total_amount))
        + _row("Net payable", _inr(expense.net_payable))
    )
    body = (
        f'<table class="kv">{rows}</table>'
        + (f"<h3>Notes</h3><p>{escape(expense.notes)}</p>" if expense.notes else "")
        + _sign("Prepared by", "Approved by")
    )
    return _shell("Expense Voucher", org_name, "Voucher #", expense.expense_number, body)
