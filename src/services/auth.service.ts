import { apiFetch } from "@/api/client";
import { ROLE_PERMISSIONS } from "@/permissions";
import type { AuthUser, Role, School } from "@/types";

export interface Session {
  user: AuthUser;
  school: School | null;
  token: string;
}

const STORAGE_KEY = "fn.session.v1";

export function readStoredSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (session?.user?.role) {
      session.user.permissions = ROLE_PERMISSIONS[session.user.role as Role];
    }
    return session;
  } catch {
    return null;
  }
}

export function persistSession(session: Session | null) {
  if (typeof window === "undefined") return;
  if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  else window.localStorage.removeItem(STORAGE_KEY);
}

export async function login(identifier: string, password: string): Promise<Session> {
  // SECURITY: Public endpoint; no authenticated permission or schoolId match is allowed.
  return apiFetch<Session>("/auth/login", { method: "POST", body: { identifier, password } });
}

export async function requestPasswordReset(email: string): Promise<{ sent: true }> {
  // SECURITY: Public endpoint; no authenticated permission or schoolId match is allowed.
  return apiFetch("/auth/password-reset", { method: "POST", body: { email } });
}

export async function resetPassword(token: string, password: string): Promise<{ ok: true }> {
  // SECURITY: Public endpoint must restrict the reset token to its single account; schoolId match does not apply.
  return apiFetch("/auth/password-reset/confirm", { method: "POST", body: { token, password } });
}

export async function logout(): Promise<void> {
  // SECURITY: Session-scoped endpoint may invalidate only the caller's own session; no permission or schoolId match applies.
  await apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
  persistSession(null);
}

export interface ProfileUpdate {
  fullName: string;
  phone: string;
}

export async function updateProfile(input: ProfileUpdate): Promise<AuthUser> {
  // SECURITY: Authenticated self-only endpoint; no tenant permission or schoolId match applies.
  return apiFetch<AuthUser>("/auth/profile", { method: "PATCH", body: input });
}

export async function changePassword(current: string, next: string): Promise<{ ok: true }> {
  // SECURITY: Authenticated self-only endpoint must require the current password; no tenant permission or schoolId match applies.
  return apiFetch<{ ok: true }>("/auth/change-password", {
    method: "POST",
    body: { current, next },
  });
}
