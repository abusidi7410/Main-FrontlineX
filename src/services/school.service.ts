import { apiFetch } from "@/api/client";
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

export async function getResultSheets(): Promise<ResultSheet[]> {
  // SECURITY: Backend must verify permission results.read and schoolId match, or allow only published own or linked-child results.
  return apiFetch("/results");
}

export async function updateResultSheetStatus(
  id: string,
  status: ResultSheet["status"],
): Promise<ResultSheet> {
  // SECURITY: Backend must verify permission results.publish for published, results.approve for approved, otherwise results.write, and schoolId match.
  return apiFetch(`/results/${id}/status`, { method: "PATCH", body: { status } });
}

export async function updateResultSheetScores(
  id: string,
  rows: ResultSheetRow[],
): Promise<ResultSheet> {
  // SECURITY: Backend must verify permission results.write and schoolId match for the sheet and every student row.
  return apiFetch(`/results/${id}`, { method: "PATCH", body: { rows } });
}

export interface ResultSheetInput {
  className: string;
  subject: string;
  term: string;
}

export async function createResultSheet(input: ResultSheetInput): Promise<ResultSheet> {
  // SECURITY: Backend must verify permission results.write and schoolId match.
  return apiFetch("/results", { method: "POST", body: input });
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
