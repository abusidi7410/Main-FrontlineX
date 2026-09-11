import { ApiRequestError, USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";
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

function buildSession(account: DemoAccount): Session {
  return {
    token: `dev.${account.role}.${Date.now()}`,
    user: {
      id: `usr_${account.role}`,
      fullName: account.fullName,
      email: account.email,
      phone: "+2348031234567",
      role: account.role,
      permissions: ROLE_PERMISSIONS[account.role],
      schoolId: account.role === "platform_manager" ? null : mock.school.id,
    },
    school: account.role === "platform_manager" ? null : mock.school,
  };
}

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
  if (!USE_MOCK_ADAPTER) {
    return apiFetch<Session>("/auth/login", { method: "POST", body: { identifier, password } });
  }
  const account = DEMO_ACCOUNTS.find((a) => a.email === identifier.trim().toLowerCase());
  if (!account) {
    throw new ApiRequestError(
      "We couldn't find an account with those details. Check your email or ask your school administrator to invite you.",
      401,
    );
  }
  if (password.length < 8) {
    throw new ApiRequestError("That password is incorrect. Please try again.", 401);
  }
  return mockDelay(buildSession(account), 650);
}

export async function requestPasswordReset(email: string): Promise<{ sent: true }> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch("/auth/password-reset", { method: "POST", body: { email } });
  return mockDelay({ sent: true } as const, 700);
}

export async function resetPassword(token: string, password: string): Promise<{ ok: true }> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch("/auth/password-reset/confirm", { method: "POST", body: { token, password } });
  return mockDelay({ ok: true } as const, 700);
}

export async function logout(): Promise<void> {
  if (!USE_MOCK_ADAPTER)
    await apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
  persistSession(null);
}

export interface ProfileUpdate {
  fullName: string;
  phone: string;
}

export async function updateProfile(input: ProfileUpdate): Promise<AuthUser> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch<AuthUser>("/auth/profile", { method: "PATCH", body: input });
  const current = readStoredSession()?.user;
  return mockDelay(
    {
      id: current?.id ?? "usr_self",
      fullName: input.fullName,
      email: current?.email ?? "you@school.edu.ng",
      phone: input.phone,
      role: current?.role ?? "school_admin",
      permissions: current?.permissions ?? [],
      schoolId: current?.schoolId ?? mock.school.id,
    } satisfies AuthUser,
    550,
  );
}

export async function changePassword(current: string, next: string): Promise<{ ok: true }> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch<{ ok: true }>("/auth/change-password", {
      method: "POST",
      body: { current, next },
    });
  if (current.length < 8) {
    throw new ApiRequestError("Your current password is incorrect.", 400);
  }
  if (current === next) {
    throw new ApiRequestError("Your new password must be different from the current one.", 400);
  }
  return mockDelay({ ok: true } as const, 750);
}
