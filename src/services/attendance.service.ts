import { apiFetch } from "@/api/client";
import type { AttendanceStatus, AttendanceSubmission, Student } from "@/types";

export type RosterParams = {
  className: string;
  arm?: string;
  date?: string;
  subject?: string;
};

export interface RosterResponse {
  students: Student[];
  taken: boolean;
  existing: Record<string, AttendanceStatus>;
}

export async function getRoster(params: RosterParams): Promise<RosterResponse> {
  return apiFetch("/attendance/roster", { query: params });
}

export async function submitAttendance(submission: AttendanceSubmission): Promise<{ id: string }> {
  return apiFetch("/attendance", {
    method: "POST",
    body: {
      className: submission.className,
      date: submission.date,
      subject: submission.subject ?? "",
      records: submission.records,
    },
  });
}