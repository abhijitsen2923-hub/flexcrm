import { useMemo } from "react";

import type { PermissionCode } from "../types/crm";
import { useAuth } from "./useAuth";


/**
 * Reads the current user's effective permission set off `useAuth`'s user
 * (populated by login/register/refresh + refreshed via `GET /me/permissions`
 * when an admin grants something mid-session).
 *
 * Returns helpers:
 *   - `has(code)` — true if the user has that single permission.
 *   - `any(codes)` — true if the user has at least one of the given codes.
 *   - `all(codes)` — true if the user has every code in the list.
 *
 * Backend still 403s on URL-typed access, so the frontend just hides
 * affordances the user can't use. No route guard.
 */
export function usePermissions() {
  const { user } = useAuth();
  const set = useMemo(
    () => new Set<string>(user?.permissions ?? []),
    [user?.permissions],
  );
  return {
    has: (code: PermissionCode) => set.has(code),
    any: (codes: PermissionCode[]) => codes.some((c) => set.has(c)),
    all: (codes: PermissionCode[]) => codes.every((c) => set.has(c)),
    effective: set,
  };
}
