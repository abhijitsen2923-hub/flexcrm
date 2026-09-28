// Where a signed-in user must go instead of the staff app page they asked for (pure — unit-tested in
// tests/staffAppRedirect.test.ts). null = they may stay.
import type { User } from "../../types/crm";

export const PLATFORM_ADMIN_HOME = "/admin";

function isAdminPath(pathname: string): boolean {
  return pathname === PLATFORM_ADMIN_HOME || pathname.startsWith(`${PLATFORM_ADMIN_HOME}/`);
}

export function staffAppRedirect(
  user: Pick<User, "role" | "is_platform_admin">,
  pathname: string
): string | null {
  // Portal-only roles never see the staff app — a broker/customer landing on "/" (or any deep link) goes
  // to their portal.
  if (user.role === "broker") return "/partner";
  if (user.role === "customer") return "/customer";
  // Platform admins only have the admin console (the sidebar and bottom nav show nothing else): after
  // login, on "/" or on any workspace deep link they land on it instead of an empty workspace Dashboard.
  if (user.is_platform_admin && !isAdminPath(pathname)) return PLATFORM_ADMIN_HOME;
  return null;
}
