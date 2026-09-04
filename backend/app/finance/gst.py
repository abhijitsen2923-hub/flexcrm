"""Pure GST computation for finance documents (expenses, vendor bills).

Phase-1 simple GST: given the amount the user typed, whether GST applies, the
rate, intra- vs inter-state treatment, and inclusive/exclusive, compute the
taxable base, the CGST/SGST or IGST split, and the payable totals (net of TDS).

Deliberately side-effect-free so it is trivially unit-testable and can be
mirrored in TypeScript for a live preview. The server is the source of truth;
the caller stores the returned snapshot on the row.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.database.enums import GstTreatment

_CENTS = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    """Quantize to 2 dp, half-up (Indian currency convention)."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class GstBreakdown:
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    tds_amount: Decimal
    net_payable: Decimal


def compute_gst(
    *,
    amount_entered: Decimal,
    gst_applicable: bool,
    gst_rate: Decimal | None,
    gst_treatment: GstTreatment | None,
    gst_inclusive: bool,
    tds_amount: Decimal | None = None,
) -> GstBreakdown:
    """Return the GST + payable breakdown for one finance document.

    - Exclusive: taxable = amount_entered; tax = taxable * rate.
    - Inclusive: taxable = amount_entered / (1 + rate); tax = amount_entered - taxable.
    - intra_state (default): CGST = SGST = tax/2 (the odd rupee goes to SGST so
      CGST + SGST == tax exactly). inter_state: IGST = tax.
    - total = taxable + tax; net_payable = total - TDS.
    """
    amount = Decimal(amount_entered)
    tds = _q(Decimal(tds_amount or 0))

    if not gst_applicable or not gst_rate:
        taxable = _q(amount)
        total = taxable
        return GstBreakdown(
            taxable_amount=taxable,
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
            total_amount=total,
            tds_amount=tds,
            net_payable=_q(total - tds),
        )

    rate = Decimal(gst_rate) / Decimal(100)
    if gst_inclusive:
        taxable = _q(amount / (Decimal(1) + rate))
        tax_total = _q(amount - taxable)
    else:
        taxable = _q(amount)
        tax_total = _q(taxable * rate)

    if gst_treatment == GstTreatment.inter_state:
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")
        igst = tax_total
    else:  # intra_state (default)
        cgst = _q(tax_total / 2)
        sgst = _q(tax_total - cgst)  # remainder → SGST, no rounding drift
        igst = Decimal("0.00")

    total = _q(taxable + cgst + sgst + igst)
    return GstBreakdown(
        taxable_amount=taxable,
        cgst_amount=cgst,
        sgst_amount=sgst,
        igst_amount=igst,
        total_amount=total,
        tds_amount=tds,
        net_payable=_q(total - tds),
    )
