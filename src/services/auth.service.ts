import { apiFetch } from "@/api/client";
import { ROLE_PERMISSIONS } from "@/permissions";
import type { AuthUser, Role, School } from "@/types";

export interface Session {
  user: AuthUser;
  school: School | null;
  token: string;
}

const STORAGE_KEY = "fn.session.v1";

export interface DemoAccount {
  role: Role;
  fullName: string;
  email: string;
  description: string;
}

/** Development accounts. In live mode the backend issues the session. */
export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    role: "school_admin",
    fullName: "Aisha Bello",
    email: "admin@alnoor.edu.ng",
    description: "Runs the entire school",
  },
  {
    role: "principal",
    fullName: "Ibrahim Danjuma",
    email: "principal@alnoor.edu.ng",
    description: "Academic oversight & approvals",
  },
  {
    role: "teacher",
    fullName: "Ibrahim Sani",
    email: "teacher@alnoor.edu.ng",
    description: "Attendance, results, lesson plans",
  },
  {
    role: "accountant",
    fullName: "Halima Yusuf",
    email: "bursar@alnoor.edu.ng",
    description: "Fees, payments, receipts",
  },
  {
    role: "secretary",
    fullName: "Grace Uche",
    email: "secretary@alnoor.edu.ng",
    description: "Registration & communication",
  },
  {
    role: "parent",
    fullName: "Mr. Abubakar",
    email: "parent@example.com",
    description: "Children, results, fees",
  },
  {
    role: "student",
    fullName: "Ahmed Abubakar",
    email: "student@alnoor.edu.ng",
    description: "Timetable, results, materials",
  },
  {
    role: "platform_manager",
    fullName: "Nexus Operations",
    email: "ops@frontlinenexus.com",
    description: "Frontline Nexus platform team",
  },
];

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
  return apiFetch<Session>("/auth/login", { method: "POST", body: { identifier, password } });
}

export async function requestPasswordReset(email: string): Promise<{ sent: true }> {
  return apiFetch("/auth/password-reset", { method: "POST", body: { email } });
}

export async function resetPassword(token: string, password: string): Promise<{ ok: true }> {
  return apiFetch("/auth/password-reset/confirm", { method: "POST", body: { token, password } });
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
  persistSession(null);
}

export interface ProfileUpdate {
  fullName: string;
  phone: string;
}

export async function updateProfile(input: ProfileUpdate): Promise<AuthUser> {
  return apiFetch<AuthUser>("/auth/profile", { method: "PATCH", body: input });
}

export async function changePassword(current: string, next: string): Promise<{ ok: true }> {
  return apiFetch<{ ok: true }>("/auth/change-password", {
    method: "POST",
    body: { current, next },
  });
}