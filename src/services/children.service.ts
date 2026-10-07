import { apiFetch, type Paginated } from "@/api/client";
import type { Student } from "@/types";

export interface ChildAttendance {
  studentId: string;
  studentName: string;
  session: string;
  summary: {
    recorded: number;
    present: number;
    late: number;
    absent: number;
    excused: number;
    /** `null` when the child has no attendance days in the window yet. */
    attendanceRate: number | null;
  };
  records: {
    date: string;
    status: "present" | "late" | "absent" | "excused";
    className: string;
  }[];
}

export interface ChildPromotion {
  enrolled: boolean;
  session: string;
  className: string;
  arm: string;
  suggested: "promote" | "conditional" | "repeat" | "review" | null;
  reason: string;
  average: number | null;
  attendanceRate: number | null;
  failedSubjects: number;
  subjectsAssessed: number;
  isFinalClass: boolean;
  nextClass: string | null;
  policy: {
    promoteMinAverage: number;
    promoteMinAttendance: number;
    conditionalMinAverage: number;
    conditionalMinAttendance: number;
    conditionalMaxFailedSubjects: number;
  } | null;
  history: {
    sessionId: string;
    session: string;
    className: string;
    arm: string;
    status: string;
    flaggedForReview: boolean;
    reviewNote: string;
  }[];
}

/**
 * The parent portal children list. Same paginated shape as the school roster,
 * but the backend answers only the students `linked_students` ties to the
 * login — a parent can never page through another family's records by raising
 * `pageSize`.
 */
export async function listChildren(
  query: { page?: number; pageSize?: number } = {},
): Promise<Paginated<Student>> {
  return apiFetch("/parents/me/children", { query });
}

/**
 * One child's attendance register for their own session window, optionally
 * narrowed to a date range. A child that is not linked to the caller is a 404
 * server-side, so no id here ever reaches another family's marks.
 */
export async function getChildAttendance(
  studentId: string,
  opts: { dateFrom?: string; dateTo?: string } = {},
): Promise<ChildAttendance> {
  return apiFetch(`/parents/me/children/${studentId}/attendance`, { query: opts });
}

/**
 * The promotion suggestion for one child, derived from the same published
 * results and attendance the head teacher's promotion screen uses.
 */
export async function getChildPromotion(studentId: string): Promise<ChildPromotion> {
  return apiFetch(`/parents/me/children/${studentId}/promotion`);
}
