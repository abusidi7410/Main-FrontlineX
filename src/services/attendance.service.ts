import { apiFetch } from "@/api/client";
import { ARMS, CLASSES } from "@/constants/reference";
import type { AttendanceSubmission, Student } from "@/types";

export async function getRoster(className: string): Promise<Student[]> {
  return apiFetch("/attendance/roster", { query: { className } });
}

export async function submitAttendance(submission: AttendanceSubmission): Promise<{ id: string }> {
  return apiFetch("/attendance", { method: "POST", body: submission });
}

export const CLASS_OPTIONS = CLASSES.flatMap((c) => ARMS.map((a) => `${c}${a}`));