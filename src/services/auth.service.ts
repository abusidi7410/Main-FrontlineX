import { apiFetch } from "@/api/client";
import { ROLE_PERMISSIONS } from "@/permissions";
import type { AuthUser, Role, School } from "@/types";

export interface Session {
  user: AuthUser;
  school: School | null;
  token: string;
}

const STORAGE_KEY = "fn.session.v1";

function getStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readStoredSession(): Session | null {
  const storage = getStorage();
  if (!storage) return null;

  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const session = JSON.parse(raw) as Partial<Session>;
    if (!session?.user || !session?.token || typeof session.token !== "string") {
      storage.removeItem(STORAGE_KEY);
      return null;
    }

    if (session.user.role) {
      session.user.permissions = ROLE_PERMISSIONS[session.user.role as Role];
    }

    return session as Session;
  } catch {
    storage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function persistSession(session: Session | null) {
  const storage = getStorage();
  if (!storage) return;

  if (session && session.token) {
    storage.setItem(STORAGE_KEY, JSON.stringify(session));
    return;
  }

  storage.removeItem(STORAGE_KEY);
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
