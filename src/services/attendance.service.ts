import { apiFetch } from "@/api/client";
import type { AttendanceStatus, AttendanceSubmission, Student } from "@/types";

export type RosterParams = {
  className: string;
  arm?: string;
  date?: string;
};

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
}

export interface SubmitAttendanceResponse {
  id: string;
  saved: number;
  skipped: number;
  byStatus: Record<string, number>;
  date: string;
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
