import { apiFetch, type Paginated } from "@/api/client";
import type {
  Announcement,
  AppNotification,
  AuditEvent,
  LessonPlan,
  LessonPlanInput,
  ResultSheet,
  ResultSheetStatus,
  ResultSheetSummary,
  ResultSheetRow,
  ResultReportEntry,
  MyPublishedResult,
  NotificationPage,
  NotificationPreference,
  NotificationType,
  School,
  StaffMember,
  SubscriptionState,
  TimetableEntry,
  TimetableEntryInput,
  TimetableGrid,
  TimetablePeriod,
  TimetablePeriodInput,
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

export type SchoolProfile = Pick<
  School,
  | "id"
  | "name"
  | "slug"
  | "logoUrl"
  | "status"
  | "address"
  | "state"
  | "lga"
  | "phone"
  | "email"
  | "branding"
  | "studentCount"
  | "staffCount"
>;

export interface SchoolProfileInput {
  name?: string;
  phone?: string;
  email?: string;
  address?: string;
}

export async function getSchoolProfile(): Promise<SchoolProfile> {
  // SECURITY: Backend always reads the school from the caller's own account;
  // there is no schoolId parameter to swap for another tenant.
  try {
    return await apiFetch<SchoolProfile>("/schools/profile");
  } catch (err) {
    // Compatibility: older backend deployment may expose the route under /schools/schools/profile/
    return await apiFetch<SchoolProfile>("/schools/schools/profile");
  }
}

export async function updateSchoolProfile(input: SchoolProfileInput): Promise<SchoolProfile> {
  // SECURITY: Backend must verify permission settings.write and derive the
  // school from the session, ignoring any id in the payload.
  try {
    return await apiFetch<SchoolProfile>("/schools/profile", { method: "PATCH", body: input });
  } catch (err) {
    return await apiFetch<SchoolProfile>("/schools/schools/profile", { method: "PATCH", body: input });
  }
}

export async function uploadSchoolLogo(logo: File): Promise<SchoolProfile> {
  // SECURITY: as updateSchoolProfile, but multipart so the image goes through
  // the normal storage field instead of being embedded in the database.
  const body = new FormData();
  body.append("logo", logo);
  try {
    return await apiFetch<SchoolProfile>("/schools/profile", { method: "PATCH", body });
  } catch (err) {
    return await apiFetch<SchoolProfile>("/schools/schools/profile", { method: "PATCH", body });
  }
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
  // SECURITY: Backend returns only the announcements this account's audience
  // covers — staff with communication.read see the whole board, parents and
  // students see their own audience. No client-side filtering is needed or safe.
  return apiFetch("/announcements");
}

export async function createAnnouncement(
  input: Omit<Announcement, "id" | "createdAt" | "author" | "scope">,
): Promise<Announcement> {
  // SECURITY: Backend must verify permission communication.write and schoolId match.
  return apiFetch("/announcements", { method: "POST", body: input });
}

export async function updateAnnouncement(
  id: string,
  patch: Partial<Pick<Announcement, "title" | "body" | "isPinned" | "expiresAt">>,
): Promise<Announcement> {
  // SECURITY: Backend must verify permission communication.write and schoolId match.
  return apiFetch(`/announcements/${id}`, { method: "PATCH", body: patch });
}

export async function deleteAnnouncement(id: string): Promise<void> {
  // SECURITY: Backend must verify permission communication.write and schoolId match.
  return apiFetch(`/announcements/${id}`, { method: "DELETE" });
}

export async function getNotifications(
  options: { unreadOnly?: boolean; type?: NotificationType; page?: number; pageSize?: number } = {},
): Promise<NotificationPage> {
  // SECURITY: Authenticated self-only endpoint; no tenant permission or schoolId match applies.
  const query: Record<string, string> = {};
  if (options.unreadOnly) query["unread"] = "true";
  if (options.type) query["type"] = options.type;
  if (options.page) query["page"] = String(options.page);
  if (options.pageSize) query["pageSize"] = String(options.pageSize);
  return apiFetch("/notifications", { query });
}

export async function markNotificationRead(id: string): Promise<AppNotification> {
  // SECURITY: Authenticated self-only endpoint; the backend scopes the lookup to
  // the caller, so another person's id is simply not found.
  return apiFetch(`/notifications/${id}/read`, { method: "POST" });
}

export async function markAllNotificationsRead(): Promise<{ markedRead: number }> {
  // SECURITY: Authenticated self-only endpoint may update only the caller's notifications; no schoolId match applies.
  return apiFetch("/notifications/read-all", { method: "POST" });
}

export async function getNotificationPreferences(): Promise<NotificationPreference[]> {
  // SECURITY: Authenticated self-only endpoint; no tenant permission or schoolId match applies.
  return apiFetch("/notifications/preferences");
}

export async function saveNotificationPreferences(
  preferences: Pick<NotificationPreference, "type" | "inApp">[],
): Promise<NotificationPreference[]> {
  // SECURITY: Authenticated self-only endpoint may update only the caller's preferences.
  return apiFetch("/notifications/preferences", {
    method: "PATCH",
    body: { preferences },
  });
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

/**
 * The weekly grid: periods, lessons in scope, and the reference lists the
 * editor needs to place one.
 *
 * The API decides what is in scope: an administrator gets the whole school, a
 * teacher their own week, a pupil or parent their own classes. Passing
 * `classId` or `teacherId` narrows it further, and a pupil or parent asking for
 * a class they are not in is refused.
 */
export async function getTimetableGrid(
  scope: { classId?: string; teacherId?: string } = {},
): Promise<TimetableGrid> {
  // SECURITY: Backend verifies timetable.read, scopes every row to the caller's
  // school, and refuses a classId the caller is not entitled to.
  return apiFetch<TimetableGrid>("/timetable", { query: scope });
}

/**
 * Lessons as a flat list, for screens that only need the rows.
 *
 * Kept for list views such as "my classes", which read `className` off each
 * slot. Prefer `getTimetableGrid` where the grid or the editor is involved.
 */
export async function getTimetable(): Promise<TimetableEntry[]> {
  const grid = await getTimetableGrid();
  return grid.entries;
}

export async function createTimetableEntry(input: TimetableEntryInput): Promise<TimetableEntry> {
  // SECURITY: Backend verifies timetable.write, rejects the class/period/teacher
  // if they belong to another school, and raises the teacher, class and room
  // conflicts as field errors rather than creating a double booking.
  return apiFetch<TimetableEntry>("/timetable/entries", { method: "POST", body: input });
}

/**
 * Change part of a lesson. Omitted fields keep their current value, so the
 * editor can move a lesson without resending the whole row.
 */
export async function updateTimetableEntry(
  id: string,
  input: Partial<TimetableEntryInput>,
): Promise<TimetableEntry> {
  // SECURITY: Backend verifies timetable.write and scopes the lesson to the
  // caller's school.
  return apiFetch<TimetableEntry>(`/timetable/entries/${id}`, {
    method: "PATCH",
    body: input,
  });
}

export async function deleteTimetableEntry(id: string): Promise<void> {
  // SECURITY: Backend verifies timetable.write and 404s a lesson from another school.
  return apiFetch<void>(`/timetable/entries/${id}`, { method: "DELETE" });
}

export async function createTimetablePeriod(input: TimetablePeriodInput): Promise<TimetablePeriod> {
  // SECURITY: Backend verifies timetable.write and resolves the period inside
  // the caller's school.
  return apiFetch<TimetablePeriod>("/timetable/periods", { method: "POST", body: input });
}

export async function updateTimetablePeriod(
  id: string,
  input: Partial<TimetablePeriodInput>,
): Promise<TimetablePeriod> {
  // SECURITY: Backend verifies timetable.write and scopes the period to the
  // caller's school.
  return apiFetch<TimetablePeriod>(`/timetable/periods/${id}`, {
    method: "PATCH",
    body: input,
  });
}

export async function deleteTimetablePeriod(id: string): Promise<void> {
  // SECURITY: Backend verifies timetable.write, 404s a period from another
  // school, and refuses to delete one that still holds lessons.
  return apiFetch<void>(`/timetable/periods/${id}`, { method: "DELETE" });
}

export async function getLessonPlans(): Promise<LessonPlan[]> {
  // SECURITY: Backend must verify permission lessonplans.read and schoolId match.
  return apiFetch("/lesson-plans");
}

export async function saveLessonPlan(plan: LessonPlanInput): Promise<LessonPlan> {
  const { id, ...input } = plan;
  if (id) {
    // SECURITY: Backend must verify permission lessonplans.write and schoolId match for the existing plan.
    return apiFetch(`/lesson-plans/${id}`, { method: "PATCH", body: input });
  }
  // SECURITY: Backend must verify permission lessonplans.write and schoolId match.
  return apiFetch("/lesson-plans", { method: "POST", body: input });
}

export async function deleteLessonPlan(id: string): Promise<void> {
  // SECURITY: Backend verifies lessonplans.write and scopes the plan to the caller's school.
  return apiFetch(`/lesson-plans/${id}`, { method: "DELETE" });
}

export async function getSchoolAuditLogs(): Promise<AuditEvent[]> {
  // SECURITY: Backend must verify permission audit.read and schoolId match.
  return apiFetch("/audit-logs");
}

export async function getUssdConfig(): Promise<UssdConfig> {
  // SECURITY: Backend must verify permission settings.read and schoolId match.
  return apiFetch("/ussd-config");
}
