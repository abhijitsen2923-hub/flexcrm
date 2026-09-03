import type { UserRole } from "../types/crm";

// Mirrors backend app/core/permissions.py ROLE_STAGE_ACCESS. Which lead stage
// codes each RESTRICTED role may move a lead TO. Roles not listed here (owner,
// sales_manager, and the education/travel roles) are unrestricted — the backend
// is the source of truth; this only trims the UI so users don't pick a stage
// they'll be 403'd on.
const FULL_ACTIVE = [
  "call", "did_not_pickup", "follow_up", "site_visit_confirmed", "site_visit_done", "interested",
  "booked", "agreement_payment", "registration", "possession",
  "not_interested", "disqualified",
];

const ROLE_STAGE_ACCESS: Partial<Record<UserRole, readonly string[]>> = {
  receptionist: ["new_enquiry", "call"],
  telecaller: ["call", "did_not_pickup", "follow_up", "not_interested", "disqualified"],
  sales_executive: FULL_ACTIVE,
  crm_team: FULL_ACTIVE,
};

export function canSetStage(role: UserRole | undefined | null, stageCode: string): boolean {
  if (!role) return true;
  const allowed = ROLE_STAGE_ACCESS[role];
  return allowed === undefined || allowed.includes(stageCode);
}
