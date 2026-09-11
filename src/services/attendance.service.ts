import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";
import type { AttendanceSubmission, Student } from "@/types";

export async function getRoster(className: string): Promise<Student[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/attendance/roster", { query: { className } });
  const roster = mock.students.filter((s) => `${s.className}${s.arm}` === className);
  return mockDelay(roster.length ? roster : mock.students.slice(0, 14), 350);
}

export async function submitAttendance(submission: AttendanceSubmission): Promise<{ id: string }> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/attendance", { method: "POST", body: submission });
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    throw new Error("offline");
  }
  return mockDelay({ id: submission.id }, 700);
}

export const CLASS_OPTIONS = mock.CLASSES.flatMap((c) => mock.ARMS.map((a) => `${c}${a}`));
