import { USE_LIVE_AUTH, USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";
import type {
  Announcement,
  AppNotification,
  AuditEvent,
  LessonPlan,
  ResultSheet,
  ResultSheetRow,
  StaffMember,
  SubscriptionState,
  TimetableSlot,
  UssdConfig,
} from "@/types";

export interface OnboardingPayload {
  school: {
    name: string;
    type: string;
    address: string;
    state: string;
    lga: string;
    phone: string;
    email: string;
    website?: string | undefined;
  };
  admin: { fullName: string; phone: string; email: string; password: string };
  tierId: string;
}

export async function registerSchool(payload: OnboardingPayload) {
  if (USE_LIVE_AUTH)
    return apiFetch<{ schoolId: string; paymentRef: string }>("/schools/register", {
      method: "POST",
      body: payload,
    });
  return mockDelay(
    { schoolId: "sch_new", paymentRef: `FN-${Date.now().toString().slice(-8)}` },
    900,
  );
}

export async function verifySchoolPayment(reference: string) {
  if (USE_LIVE_AUTH)
    return apiFetch<{ status: "verified" | "pending" }>(`/payments/${reference}/verify`);
  return mockDelay({ status: "verified" as const }, 1600);
}

export async function getSubscription(): Promise<SubscriptionState> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/subscription");
  return mockDelay(mock.subscription);
}

export async function getStaff(): Promise<StaffMember[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/staff");
  return mockDelay(mock.staff);
}

export async function getAnnouncements(): Promise<Announcement[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/announcements");
  return mockDelay(mock.announcements);
}

export async function createAnnouncement(
  input: Omit<Announcement, "id" | "createdAt" | "author">,
): Promise<Announcement> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/announcements", { method: "POST", body: input });
  const created: Announcement = {
    ...input,
    id: `ann_${Date.now()}`,
    createdAt: new Date().toISOString(),
    author: "You",
  };
  mock.announcements.unshift(created);
  return mockDelay(created, 600);
}

export async function getNotifications(): Promise<AppNotification[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/notifications");
  return mockDelay(mock.notifications, 300);
}

export async function markAllNotificationsRead(): Promise<void> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/notifications/read-all", { method: "POST" });
  mock.notifications.forEach((n) => (n.read = true));
  return mockDelay(undefined, 250);
}

export async function getResultSheets(): Promise<ResultSheet[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/results");
  return mockDelay(mock.resultSheets);
}

export async function updateResultSheetStatus(
  id: string,
  status: ResultSheet["status"],
): Promise<ResultSheet> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/results/${id}/status`, { method: "PATCH", body: { status } });
  const sheet = mock.resultSheets.find((s) => s.id === id)!;
  sheet.status = status;
  return mockDelay(sheet, 500);
}

export async function updateResultSheetScores(
  id: string,
  rows: ResultSheetRow[],
): Promise<ResultSheet> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/results/${id}`, { method: "PATCH", body: { rows } });
  const sheet = mock.resultSheets.find((s) => s.id === id);
  if (!sheet) throw new Error("We couldn't find that result sheet.");
  const byId = new Map(rows.map((row) => [row.studentId, row]));
  sheet.rows = sheet.rows.map((existing) => {
    const incoming = byId.get(existing.studentId);
    if (!incoming) return existing;
    return {
      ...existing,
      ca1: incoming.ca1,
      ca2: incoming.ca2,
      assignment: incoming.assignment,
      exam: incoming.exam,
    };
  });
  return mockDelay(sheet, 500);
}

export interface ResultSheetInput {
  className: string;
  subject: string;
  term: string;
}

export async function createResultSheet(input: ResultSheetInput): Promise<ResultSheet> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/results", { method: "POST", body: input });
  const existing = mock.resultSheets.find(
    (s) => s.className === input.className && s.subject === input.subject && s.term === input.term,
  );
  if (existing) {
    throw new Error(
      `A ${input.className} ${input.subject} sheet already exists for ${input.term}.`,
    );
  }
  const rows: ResultSheetRow[] = mock.students
    .filter((s) => s.className === input.className)
    .map((s) => ({
      studentId: s.id,
      studentName: `${s.firstName} ${s.lastName}`,
      ca1: null,
      ca2: null,
      assignment: null,
      exam: null,
    }));
  const created: ResultSheet = {
    id: `rs_${Date.now()}`,
    className: input.className,
    subject: input.subject,
    term: input.term,
    status: "draft",
    rows,
  };
  mock.resultSheets.push(created);
  return mockDelay(created, 500);
}

export async function getTimetable(): Promise<TimetableSlot[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/timetable");
  return mockDelay(mock.timetable);
}

export async function getLessonPlans(): Promise<LessonPlan[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/lesson-plans");
  return mockDelay(mock.lessonPlans);
}

export async function saveLessonPlan(
  plan: Omit<LessonPlan, "id" | "updatedAt"> & { id?: string },
): Promise<LessonPlan> {
  if (!USE_MOCK_ADAPTER) {
    return plan.id
      ? apiFetch(`/lesson-plans/${plan.id}`, { method: "PATCH", body: plan })
      : apiFetch("/lesson-plans", { method: "POST", body: plan });
  }
  const saved: LessonPlan = {
    ...plan,
    id: plan.id ?? `lp_${Date.now()}`,
    updatedAt: new Date().toISOString(),
  };
  const idx = mock.lessonPlans.findIndex((p) => p.id === saved.id);
  if (idx >= 0) mock.lessonPlans[idx] = saved;
  else mock.lessonPlans.unshift(saved);
  return mockDelay(saved, 500);
}

const AUDIT_SOURCE: Array<Omit<AuditEvent, "id" | "createdAt">> = [
  {
    actor: "Mrs. Aisha Bello",
    role: "school_admin",
    action: "student.created",
    detail: "Registered new student Ahmed Yusuf in Primary 4A",
    ip: "102.89.45.12",
  },
  {
    actor: "Halima Yusuf",
    role: "accountant",
    action: "payment.recorded",
    detail: "Recorded ₦45,000 fee payment for Fatima Abubakar",
    ip: "102.89.45.12",
  },
  {
    actor: "Ibrahim Sani",
    role: "teacher",
    action: "results.submitted",
    detail: "Submitted JSS 2A Mathematics result sheet",
    ip: "105.112.208.7",
  },
  {
    actor: "Mrs. Aisha Bello",
    role: "school_admin",
    action: "subscription.renewed",
    detail: "Renewed 401–600 student plan for another term",
    ip: "102.89.45.12",
  },
  {
    actor: "Grace Uche",
    role: "secretary",
    action: "announcement.created",
    detail: "Published PTA meeting announcement",
    ip: "102.89.45.12",
  },
  {
    actor: "Ibrahim Danjuma",
    role: "principal",
    action: "results.approved",
    detail: "Approved Primary 5A English Language result sheet",
    ip: "105.112.208.7",
  },
  {
    actor: "System",
    role: "school_admin",
    action: "settings.updated",
    detail: "Changed branding colours and term dates",
    ip: "0.0.0.0",
  },
  {
    actor: "Mr. Abubakar",
    role: "parent",
    action: "payment.initiated",
    detail: "Initiated bank transfer for Nura Abubakar's school fees",
    ip: "154.117.129.3",
  },
];

export async function getSchoolAuditLogs(): Promise<AuditEvent[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/audit-logs");
  const now = Date.now();
  return mockDelay(
    AUDIT_SOURCE.map((event, i) => ({
      ...event,
      id: `aud_${i}`,
      createdAt: new Date(now - i * 7200_000).toISOString(),
    })),
    450,
  );
}

export async function getUssdConfig(): Promise<UssdConfig> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/ussd-config");
  return mockDelay(
    {
      enabled: true,
      shortCode: "*347#",
      fullCode: "*347*2153#",
      commands: [
        {
          code: "1",
          description: "Check my children's fee balance — each child is listed with its balance.",
        },
        {
          code: "2",
          description: "Pay school fees using your linked card, wallet or bank account.",
        },
        {
          code: "3",
          description: "Request this term's result summary by SMS for each child.",
        },
        {
          code: "4",
          description: "Get this term's attendance summary for each child.",
        },
        {
          code: "0",
          description: "Speak to the school office.",
        },
      ],
    },
    450,
  );
}
