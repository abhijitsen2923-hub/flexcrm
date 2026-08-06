/**
 * Build-time feature flags — platform-level on/off switches.
 *
 * Driven by `VITE_FEATURE_*_ENABLED` env vars. Default is OFF.
 * A module set to false here is OFF for *all* tenants regardless of their
 * org-level setting. In production all deployed modules should be `true` here
 * so per-org module access is controlled solely by the platform-admin UI.
 *
 * Per-org runtime access is layered on top via OrgContext / useOrgModules().
 * Use mergeModules(orgModules) to combine both layers — a module is active only
 * when this flag is true AND the org has it enabled.
 */

import type { ModuleKey } from "../types/crm";


const flag = (raw: string | undefined): boolean => raw === "true" || raw === "1";

export const FEATURES: Record<ModuleKey, boolean> = {
  deals: flag(import.meta.env.VITE_FEATURE_DEALS_ENABLED),
  tasks: flag(import.meta.env.VITE_FEATURE_TASKS_ENABLED),
  activities: flag(import.meta.env.VITE_FEATURE_ACTIVITIES_ENABLED),
  finance: flag(import.meta.env.VITE_FEATURE_FINANCE_ENABLED),
  hr: flag(import.meta.env.VITE_FEATURE_HR_ENABLED),
  // Real-estate modules
  inventory: flag(import.meta.env.VITE_FEATURE_INVENTORY_ENABLED),
  bookings: flag(import.meta.env.VITE_FEATURE_BOOKINGS_ENABLED),
  site_visits: flag(import.meta.env.VITE_FEATURE_SITE_VISITS_ENABLED),
  projects: flag(import.meta.env.VITE_FEATURE_PROJECTS_ENABLED),
  // Integrations
  meta_leads: flag(import.meta.env.VITE_FEATURE_META_LEADS_ENABLED),
};

export type FeatureKey = ModuleKey;

/**
 * Merge platform-level build flags with org-level runtime flags.
 * A module is active only when both layers agree it is on.
 */
export function mergeModules(orgModules: Record<ModuleKey, boolean>): Record<ModuleKey, boolean> {
  const keys: ModuleKey[] = [
    "deals", "tasks", "activities", "finance", "hr",
    "inventory", "bookings", "site_visits", "projects",
  ];
  return Object.fromEntries(
    keys.map((k) => [k, FEATURES[k] && (orgModules[k] ?? false)])
  ) as Record<ModuleKey, boolean>;
}
