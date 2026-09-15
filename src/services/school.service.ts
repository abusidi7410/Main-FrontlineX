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
  return apiFetch<{ schoolId: string; paymentRef: string }>("/schools/register", {
    method: "POST",
    body: payload,
  });
}

export async function verifySchoolPayment(reference: string) {
  return apiFetch<{ status: "verified" | "pending" }>(`/payments/${reference}/verify`);
}

export async function getSubscription(): Promise<SubscriptionState> {
  return apiFetch("/subscription");
}

export async function getStaff(): Promise<StaffMember[]> {
  return apiFetch("/staff");
}

export async function getAnnouncements(): Promise<Announcement[]> {
  return apiFetch("/announcements");
}

export async function createAnnouncement(
  input: Omit<Announcement, "id" | "createdAt" | "author">,
): Promise<Announcement> {
  return apiFetch("/announcements", { method: "POST", body: input });
}

export async function getNotifications(): Promise<AppNotification[]> {
  return apiFetch("/notifications");
}

export async function markAllNotificationsRead(): Promise<void> {
  return apiFetch("/notifications/read-all", { method: "POST" });
}

export async function getResultSheets(): Promise<ResultSheet[]> {
  return apiFetch("/results");
}

export async function updateResultSheetStatus(
  id: string,
  status: ResultSheet["status"],
): Promise<ResultSheet> {
  return apiFetch(`/results/${id}/status`, { method: "PATCH", body: { status } });
}

export async function updateResultSheetScores(
  id: string,
  rows: ResultSheetRow[],
): Promise<ResultSheet> {
  return apiFetch(`/results/${id}`, { method: "PATCH", body: { rows } });
}

export interface ResultSheetInput {
  className: string;
  subject: string;
  term: string;
}

export async function createResultSheet(input: ResultSheetInput): Promise<ResultSheet> {
  return apiFetch("/results", { method: "POST", body: input });
}

export async function getTimetable(): Promise<TimetableSlot[]> {
  return apiFetch("/timetable");
}

export async function getLessonPlans(): Promise<LessonPlan[]> {
  return apiFetch("/lesson-plans");
}

export async function saveLessonPlan(
  plan: Omit<LessonPlan, "id" | "updatedAt"> & { id?: string },
): Promise<LessonPlan> {
  return plan.id
    ? apiFetch(`/lesson-plans/${plan.id}`, { method: "PATCH", body: plan })
    : apiFetch("/lesson-plans", { method: "POST", body: plan });
}

export async function getSchoolAuditLogs(): Promise<AuditEvent[]> {
  return apiFetch("/audit-logs");
}

export async function getUssdConfig(): Promise<UssdConfig> {
  return apiFetch("/ussd-config");
}