"""HR package — EmployeeProfile + PerformanceSnapshot.

Read-only relative to the rest of the system: snapshots are computed by a
nightly job that reads SalesOrders, Invoices, Leads, and StageTransitions.
"""
