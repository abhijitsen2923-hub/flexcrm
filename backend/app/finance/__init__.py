"""Finance package — SalesOrder, Invoice, Payment, CommissionLedger, Refund.

Driven by `lead.stage_changed → sold` events from `app.services.stage_transitions`.
The Lead pipeline never reaches this package directly — it just emits events.
"""
