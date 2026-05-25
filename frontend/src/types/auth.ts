import type { LeadIndustry, User, UserRole } from "./crm";


export interface RegisterPayload {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone?: string | null;
  role?: UserRole;
  business_type: LeadIndustry;
  // Optional — defaults server-side to "{first_name}'s Workspace".
  organization_name?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RefreshPayload {
  refresh_token: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  access_token_expires_at: string;
  refresh_token_expires_at: string;
  user: User;
}

export interface StoredSession {
  accessToken: string;
  refreshToken: string;
  accessTokenExpiresAt: string;
  refreshTokenExpiresAt: string;
}
