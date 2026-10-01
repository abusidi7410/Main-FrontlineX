import { apiFetch, type Paginated } from "@/api/client";
import type {
  Announcement,
  AppNotification,
  AuditEvent,
  LessonPlan,
  ResultSheet,
  ResultSheetStatus,
  ResultSheetSummary,
  ResultSheetRow,
  ResultReportEntry,
  MyPublishedResult,
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
  // SECURITY: Public onboarding endpoint; no authenticated permission or existing schoolId match is allowed.
  return apiFetch<{ schoolId: string; paymentRef: string }>("/schools/register", {
    method: "POST",
    body: payload,
  });
}

export async function verifySchoolPayment(reference: string) {
  // SECURITY: Public payment-verification endpoint; no authenticated permission or schoolId match is allowed.
  return apiFetch<{ status: "verified" | "pending" }>(`/payments/${reference}/verify`);
}

export async function getSubscription(): Promise<SubscriptionState> {
  // SECURITY: Backend must verify permission subscription.read and schoolId match.
  return apiFetch("/subscription");
}

export async function getStaff(): Promise<StaffMember[]> {
  // SECURITY: Backend must verify permission staff.read and schoolId match.
  return apiFetch("/staff");
}

export async function getAnnouncements(): Promise<Announcement[]> {
  // SECURITY: Backend must verify permission communication.read and schoolId match, or allow audience-filtered self-service.
  return apiFetch("/announcements");
}

export async function createAnnouncement(
  input: Omit<Announcement, "id" | "createdAt" | "author">,
): Promise<Announcement> {
  // SECURITY: Backend must verify permission communication.write and schoolId match.
  return apiFetch("/announcements", { method: "POST", body: input });
}

export async function getNotifications(): Promise<AppNotification[]> {
  // SECURITY: Authenticated self-only endpoint; no tenant permission or schoolId match applies.
  return apiFetch("/notifications");
}

export async function markAllNotificationsRead(): Promise<void> {
  // SECURITY: Authenticated self-only endpoint may update only the caller's notifications; no schoolId match applies.
  return apiFetch("/notifications/read-all", { method: "POST" });
}

export async function getResultSheets(): Promise<ResultSheetSummary[]> {
  const page = await getResultSheetPage();
  return page.results;
}

export async function getResultSheetPage(
  page = 1,
  pageSize = 25,
): Promise<Paginated<ResultSheetSummary>> {
  // SECURITY: Backend enforces results.read and caller school scope.
  return apiFetch("/results", { query: { page, pageSize } });
}

export async function getResultSheet(id: string): Promise<ResultSheet> {
  // SECURITY: Backend enforces results.read and caller school scope.
  return apiFetch(`/results/${id}`);
}

export async function getPublishedResultReport(): Promise<ResultReportEntry[]> {
  const rows: ResultReportEntry[] = [];
  let page = 1;
  let totalPages = 1;
  do {
    const result = await apiFetch<Paginated<ResultReportEntry>>("/results/report", {
      query: { page, pageSize: 100 },
    });
    rows.push(...result.results);
    totalPages = result.totalPages;
    page += 1;
  } while (page <= totalPages);
  return rows;
}

export async function getMyPublishedResults(): Promise<MyPublishedResult[]> {
  const rows: MyPublishedResult[] = [];
  let page = 1;
  let totalPages = 1;
  do {
    const result = await apiFetch<Paginated<MyPublishedResult>>("/results/children", {
      query: { page, pageSize: 100 },
    });
    rows.push(...result.results);
    totalPages = result.totalPages;
    page += 1;
  } while (page <= totalPages);
  return rows;
}

export async function updateResultSheetStatus(
  id: string,
  status: ResultSheetStatus,
): Promise<ResultSheet> {
  const actionByStatus: Partial<Record<ResultSheetStatus, string>> = {
    submitted: "submit",
    under_review: "review",
    approved: "approve",
    published: "publish",
    locked: "lock",
  };
  const action = actionByStatus[status];
  if (!action) throw new Error(`Cannot transition a result sheet to ${status}.`);
  return apiFetch(`/results/${id}/action`, { method: "POST", body: { action } });
}

export async function updateResultSheetScores(
  id: string,
  rows: ResultSheetRow[],
): Promise<ResultSheet> {
  // SECURITY: Backend verifies results.write and sheet membership for every student.
  const termScores = Object.fromEntries(
    rows.map(({ studentId, ca1, ca2, assignment, exam }) => [
      studentId,
      { ca1, ca2, assignment, exam },
    ]),
  );
  return apiFetch(`/results/${id}/action`, {
    method: "POST",
    body: { action: "scores", termScores },
  });
}

export async function requestResultCorrection(id: string, reason: string): Promise<ResultSheet> {
  return apiFetch(`/results/${id}/action`, {
    method: "POST",
    body: { action: "request-correction", reason },
  });
}

export async function releaseResultCorrection(id: string): Promise<ResultSheet> {
  return apiFetch(`/results/${id}/action`, {
    method: "POST",
    body: { action: "release-correction" },
  });
}

export interface ResultSheetInput {
  classId: string;
  subject: string;
  term: string;
}

export async function createResultSheet(input: ResultSheetInput): Promise<ResultSheet> {
  // SECURITY: Backend enforces results.write and resolves the class inside caller's school.
  return apiFetch("/results/create", { method: "POST", body: input });
}

export async function getTimetable(): Promise<TimetableSlot[]> {
  // SECURITY: Backend must verify permission timetable.read and schoolId match, or restrict students and teachers to assigned entries.
  return apiFetch("/timetable");
}

export async function getLessonPlans(): Promise<LessonPlan[]> {
  // SECURITY: Backend must verify permission lessonplans.read and schoolId match.
  return apiFetch("/lesson-plans");
}

export async function saveLessonPlan(
  plan: Omit<LessonPlan, "id" | "updatedAt"> & { id?: string },
): Promise<LessonPlan> {
  if (plan.id) {
    // SECURITY: Backend must verify permission lessonplans.write and schoolId match for the existing plan.
    return apiFetch(`/lesson-plans/${plan.id}`, { method: "PATCH", body: plan });
  }
  // SECURITY: Backend must verify permission lessonplans.write and schoolId match.
  return apiFetch("/lesson-plans", { method: "POST", body: plan });
}

export async function getSchoolAuditLogs(): Promise<AuditEvent[]> {
  // SECURITY: Backend must verify permission audit.read and schoolId match.
  return apiFetch("/audit-logs");
}

export async function getUssdConfig(): Promise<UssdConfig> {
  // SECURITY: Backend must verify permission settings.read and schoolId match.
  return apiFetch("/ussd-config");
}
