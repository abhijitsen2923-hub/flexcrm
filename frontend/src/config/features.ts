/**
 * Build-time feature flags for modules that aren't ready to ship to end users.
 *
 * Driven by `VITE_FEATURE_*_ENABLED` env vars in `frontend/.env`. Default is
 * OFF — the shipped build hides every flagged module's sidebar entry and
 * route. To enable a module once it's polished and tested, flip its env var
 * to `true` and rebuild.
 *
 * Backend endpoints stay reachable regardless — these flags only gate the
 * end-user UI. Analytics and the core modules (Dashboard, Leads, Customers,
 * Users) are intentionally not here; they ship enabled.
 */

const flag = (raw: string | undefined): boolean => raw === "true" || raw === "1";

export const FEATURES = {
  deals: flag(import.meta.env.VITE_FEATURE_DEALS_ENABLED),
  tasks: flag(import.meta.env.VITE_FEATURE_TASKS_ENABLED),
  activities: flag(import.meta.env.VITE_FEATURE_ACTIVITIES_ENABLED),
  finance: flag(import.meta.env.VITE_FEATURE_FINANCE_ENABLED),
  hr: flag(import.meta.env.VITE_FEATURE_HR_ENABLED),
} as const;

export type FeatureKey = keyof typeof FEATURES;
