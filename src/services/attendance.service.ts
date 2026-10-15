import { apiFetch } from "@/api/client";
import type {
  AttendanceStatus,
  AttendanceSubmission,
  StaffAttendanceCheckInInput,
  StaffAttendancePage,
  StaffAttendanceRecord,
  StaffAttendanceStatus,
  Student,
} from "@/types";

export type RosterParams = {
  className: string;
  arm?: string;
  date?: string;
};

export interface RosterBillingQuote {
  balanceKobo: number;
  priceKobo: number;
  entitledCount: number;
  unpaidCount: number;
  coverableCount: number;
  shortfallKobo: number;
}

export interface RosterResponse {
  students: Student[];
  date: string;
  taken: boolean;
  existing: Record<string, AttendanceStatus>;
  classId: number | null;
  className: string;
  classConfigured: boolean;
  sections: string[];
  classTeacher: string;
  isSchoolDay: boolean;
  canSubmit: boolean;
  billing: RosterBillingQuote;
}

export interface SubmitAttendanceBilling {
  activated: { studentId: string; studentName: string; admissionNumber: string }[];
  skippedUnfunded: { studentId: string; studentName: string; admissionNumber: string }[];
  chargedKobo: number;
  shortfallKobo: number;
}

export interface SubmitAttendanceResponse {
  id: string;
  saved: number;
  skipped: number;
  byStatus: Record<string, number>;
  date: string;
  billing: SubmitAttendanceBilling;
}

export interface AttendanceOverviewRow {
  classId: number;
  className: string;
  submitted: number;
  present: number;
  absent: number;
  late: number;
  excused: number;
}

export interface AttendanceOverviewResponse {
  date: string;
  isSchoolDay: boolean;
  classes: AttendanceOverviewRow[];
  submitted: number;
  total: number;
}

export interface AttendanceHistoryEntry {
  id: number;
  studentId: string;
  studentName: string;
  admissionNumber: string;
  className: string;
  date: string;
  status: AttendanceStatus;
  submittedBy: string;
  updatedAt: string;
}

export async function getRoster(params: RosterParams): Promise<RosterResponse> {
  // SECURITY: Backend must verify permission attendance.read and schoolId match.
  return apiFetch("/attendance/roster", { query: params });
}

export async function submitAttendance(
  submission: AttendanceSubmission,
): Promise<SubmitAttendanceResponse> {
  // SECURITY: Backend must verify permission attendance.write, that the caller is
  // the class's designated teacher, and that schoolId matches.
  return apiFetch("/attendance", {
    method: "POST",
    body: {
      className: submission.className,
      date: submission.date,
      ...(submission.arm ? { arm: submission.arm } : {}),
      records: submission.records,
    },
  });
}

export async function getAttendanceOverview(date?: string): Promise<AttendanceOverviewResponse> {
  // SECURITY: Backend must verify permission attendance.read and schoolId match.
  return apiFetch("/attendance/overview", { query: date ? { date } : {} });
}

export async function getAttendanceHistory(params: {
  className?: string;
  studentId?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}): Promise<{
  records: AttendanceHistoryEntry[];
  count: number;
  page: number;
  pageSize: number;
  totalPages: number;
}> {
  // SECURITY: Backend must verify permission attendance.read and schoolId match.
  return apiFetch("/attendance/history", { query: params });
}

export async function correctAttendance(params: {
  recordId: string;
  status: AttendanceStatus;
  reason: string;
}): Promise<{ changed: boolean; previousStatus?: AttendanceStatus; status: AttendanceStatus }> {
  // SECURITY: Backend must verify permission attendance.correct and schoolId match.
  return apiFetch("/attendance/correct", { method: "POST", body: params });
}

export interface ClassTeacherAssignment {
  className: string;
  classId: number;
  staffId: string;
  staffName: string;
  session: string;
}

export async function getClassTeachers(): Promise<{
  session: string;
  assignments: ClassTeacherAssignment[];
}> {
  // SECURITY: Backend scopes to the caller's school and current session.
  return apiFetch("/attendance/class-teachers");
}

export async function assignClassTeacher(params: {
  className: string;
  staffId?: string;
  assign?: boolean;
}): Promise<{ className: string; classTeacher: string }> {
  // SECURITY: Backend requires staff.write, so only an administrator can change
  // who is responsible for a register. Reads are attendance.read.
  return apiFetch("/attendance/class-teachers", { method: "POST", body: params });
}

/**
 * The caller checks themselves in. The staff record is taken from the session
 * on the server, so no staff id is sent — nobody can check in for anyone else.
 */
export async function checkInStaff(
  input: StaffAttendanceCheckInInput,
): Promise<StaffAttendanceRecord> {
  // SECURITY: Backend requires attendance.staff and resolves the staff record
  // from the caller's own account.
  return apiFetch("/attendance/check-in", { method: "POST", body: input });
}

/**
 * Staff check-ins. An administrator/principal sees the whole school; everyone
 * else receives only their own rows, scoped by the server.
 */
export async function getStaffAttendance(
  params: {
    date?: string;
    dateFrom?: string;
    dateTo?: string;
    staffId?: string;
    status?: StaffAttendanceStatus[];
    search?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<StaffAttendancePage> {
  // SECURITY: Backend requires attendance.staff and scopes non-managers to
  // their own records.
  const query: Record<string, string | number | undefined> = {};
  if (params.date) query["date"] = params.date;
  if (params.dateFrom) query["dateFrom"] = params.dateFrom;
  if (params.dateTo) query["dateTo"] = params.dateTo;
  if (params.staffId) query["staffId"] = params.staffId;
  if (params.status?.length) query["status"] = params.status.join(",");
  if (params.search) query["search"] = params.search;
  if (params.page) query["page"] = params.page;
  if (params.pageSize) query["pageSize"] = params.pageSize;
  return apiFetch("/attendance/staff-records", { query });
}

export async function reviewStaffAttendance(params: {
  id: string;
  decision: "approve" | "reject";
  note?: string;
}): Promise<StaffAttendanceRecord> {
  // SECURITY: Backend requires attendance.staff.manage and scopes the record to
  // the caller's own school.
  return apiFetch(`/attendance/staff-records/${params.id}/review`, {
    method: "POST",
    body: { decision: params.decision, ...(params.note ? { note: params.note } : {}) },
  });
}

// ── Teacher class check-ins (timetabled sessions) ───────────────────────────

/** Statuses a teacher class check-in row can hold, per the spec's states. */
export type TeacherCheckInStatus =
  "present_verified" | "late_verified" | "unverified" | "outside" | "missed" | "cancelled";

/** A session's state before any check-in exists: only its absence says this. */
export type TeacherSessionStatus = TeacherCheckInStatus | "not_checked_in";

/**
 * Spec labels and tones for every state. `not_checked_in` is deliberately
 * neutral — it is the normal state of a lesson that hasn't happened yet, not
 * an accusation.
 */
export const TEACHER_CHECKIN_META: Record<
  TeacherSessionStatus,
  { label: string; className: string; dot: string }
> = {
  not_checked_in: {
    label: "Not Checked In",
    className: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
  },
  present_verified: {
    label: "Present — Location Verified",
    className: "bg-success-soft text-success",
    dot: "bg-success",
  },
  late_verified: {
    label: "Late — Location Verified",
    className: "bg-warning-soft text-warning",
    dot: "bg-warning",
  },
  unverified: {
    label: "Location Unverified",
    className: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
  },
  outside: {
    label: "Outside Approved Location",
    className: "bg-destructive/10 text-destructive",
    dot: "bg-destructive",
  },
  missed: {
    label: "Missed Class",
    className: "bg-destructive/10 text-destructive",
    dot: "bg-destructive",
  },
  cancelled: {
    label: "Class Cancelled",
    className: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
  },
};

export interface TeacherClassSession {
  entryId: number;
  className: string;
  subject: string;
  room: string;
  period: string;
  date: string;
  weekday: number;
  scheduledStart: string;
  scheduledEnd: string;
  scheduledAt: string;
  checkInAt: string | null;
  minutesLate: number | null;
  status: TeacherSessionStatus;
  gpsStatus: string;
  distanceMeters: number | null;
  studentRegisterTaken: boolean;
  canCheckIn: boolean;
}

export interface TeacherMyDayResponse {
  date: string;
  graceMinutes: number;
  staffName: string;
  sessions: TeacherClassSession[];
  summary: Record<string, number> & { total: number };
}

export interface TeacherCheckInRow {
  id: number;
  staffId: string;
  staffName: string;
  entryId: number | null;
  date: string;
  period: string;
  scheduledStart: string;
  scheduledEnd: string;
  className: string;
  subject: string;
  room: string;
  checkInAt: string | null;
  minutesLate: number | null;
  status: TeacherCheckInStatus;
  gpsStatus: string;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  distanceMeters: number | null;
  lateAlertSent: boolean;
  decidedBy: string;
  decisionNote: string;
  decidedAt: string | null;
}

/** A check-in response: the row, plus whether the server refused it. */
export interface TeacherCheckInResult extends TeacherCheckInRow {
  denied?: boolean;
  deniedReason?: string;
}

export interface TeacherCheckInPage {
  records: TeacherCheckInRow[];
  count: number;
  page: number;
  pageSize: number;
  totalPages: number;
  summary: { total: number; counts: Record<string, number> };
}

/**
 * This teacher's lessons for a day (default: the server's today) paired with
 * any check-in already recorded. The day comes from the school's clock, so a
 * device set to the wrong date cannot claim another day's lessons.
 */
export async function getMyClassAttendance(): Promise<TeacherMyDayResponse> {
  // SECURITY: Backend requires attendance.staff and resolves the staff record
  // from the caller's own account; only their own lessons are returned.
  return apiFetch("/attendance/teacher-checkins/my-day");
}

/**
 * Check in to one timetabled lesson. Only coordinates are sent — the lesson,
 * teacher and school are proved server-side against the timetable.
 */
export async function checkInToClass(input: {
  entryId: number;
  latitude?: number;
  longitude?: number;
  accuracy?: number;
}): Promise<TeacherCheckInResult> {
  // SECURITY: Backend requires attendance.staff and refuses lessons that are
  // not the caller's, not today's, or outside the campus fence.
  return apiFetch("/attendance/teacher-checkins/check-in", { method: "POST", body: input });
}

/**
 * The admin monitoring board: one row per lesson-session, filterable by date,
 * teacher, class, subject and status. Server-scoped to this school.
 */
export async function getTeacherCheckIns(
  params: {
    date?: string;
    staffId?: string;
    className?: string;
    subject?: string;
    status?: TeacherCheckInStatus[];
    search?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<TeacherCheckInPage> {
  // SECURITY: Backend requires attendance.staff.manage, so a teacher never
  // reaches this list.
  const query: Record<string, string | number | undefined> = {};
  if (params.date) query["date"] = params.date;
  if (params.staffId) query["staffId"] = params.staffId;
  if (params.className) query["className"] = params.className;
  if (params.subject) query["subject"] = params.subject;
  if (params.status?.length) query["status"] = params.status.join(",");
  if (params.search) query["search"] = params.search;
  if (params.page) query["page"] = params.page;
  if (params.pageSize) query["pageSize"] = params.pageSize;
  return apiFetch("/attendance/teacher-checkins", { query });
}

/**
 * An administrator's decision on one session: `cancel` (the lesson did not
 * run) or `override` (force a state with a required reason). Both are audited.
 */
export async function decideTeacherCheckIn(params: {
  id: number;
  action: "cancel" | "override";
  status?: "present_verified" | "late_verified" | "unverified";
  note?: string;
}): Promise<TeacherCheckInRow> {
  // SECURITY: Backend requires attendance.staff.manage and scopes the record
  // to the caller's own school.
  return apiFetch(`/attendance/teacher-checkins/${params.id}/decision`, {
    method: "POST",
    body: {
      action: params.action,
      ...(params.status ? { status: params.status } : {}),
      ...(params.note ? { note: params.note } : {}),
    },
  });
}

/**
 * The class names one staff member is the designated class teacher of, in
 * assignment order and without duplicates. The register screen defaults a
 * teacher to the first of these instead of the first class in the school, so
 * "take attendance" opens on their own class. Empty when the caller has no
 * linked staff record (admins) or no designation yet.
 */
export function assignedClassNames(
  assignments: ClassTeacherAssignment[],
  staffId: string | null | undefined,
): string[] {
  if (!staffId) return [];
  const names: string[] = [];
  for (const assignment of assignments) {
    if (assignment.staffId === staffId && !names.includes(assignment.className)) {
      names.push(assignment.className);
    }
  }
  return names;
}

/**
 * The class names shown on the "My classes" screen. A scoped teacher sees only
 * the classes they are the designated class teacher of; everyone else sees the
 * timetable-derived list. Sorted and deduped so the cards render in a stable
 * order either way.
 */
export function visibleClassNames(
  timetableNames: string[],
  assignedNames: string[],
  scoped: boolean,
): string[] {
  return Array.from(new Set(scoped ? assignedNames : timetableNames)).sort();
}
