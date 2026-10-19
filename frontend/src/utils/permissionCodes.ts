// Every permission a custom role or an individual grant can hold, in the order the Users screens show them.
// Mirrors backend PermissionCode (app/core/permissions.py).

export const ALL_PERMISSION_CODES: ReadonlyArray<string> = [
  "DASHBOARD_VIEW",
  "LEAD_VIEW", "LEAD_MANAGE", "LEAD_IMPORT",
  "CAMPAIGN_MANAGE",
  "CUSTOMER_VIEW", "CUSTOMER_MANAGE",
  "DEAL_VIEW", "DEAL_MANAGE",
  "TASK_VIEW", "TASK_MANAGE",
  "ACTIVITY_VIEW", "ACTIVITY_MANAGE",
  "FINANCE_VIEW", "FINANCE_RECORD_PAYMENT", "FINANCE_REFUND",
  "FINANCE_EXPENSE_SUBMIT", "FINANCE_EXPENSE_APPROVE", "FINANCE_VENDOR_MANAGE", "FINANCE_SETTINGS_MANAGE",
  "HR_VIEW", "HR_MANAGE",
  "USER_VIEW", "USER_MANAGE",
  "ORG_MANAGE",
  "ANALYTICS_VIEW", "REPORTS_VIEW",
  "EXPORT_DATA",
];

// LEAD_DOCS_MANAGE (Travel visa documents) isn't offered for new grants: FlexCRM is real estate only and no
// screen uses it. Where it is already granted it still shows, so it can be revoked.
export const HIDDEN_PERMISSION_CODES: ReadonlyArray<string> = ["LEAD_DOCS_MANAGE"];
