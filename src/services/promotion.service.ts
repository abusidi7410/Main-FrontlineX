import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";
import type { Student } from "@/types";

export type PromotionDecision = "promote" | "repeat" | "review";

export interface PromotionCandidate {
  studentId: string;
  studentName: string;
  admissionNumber: string;
  className: string;
  average: number;
  attendanceRate: number;
  suggested: PromotionDecision;
}

export interface PromotionClassSummary {
  className: string;
  nextClass: string | null;
  total: number;
  promote: number;
  repeat: number;
  review: number;
}

export interface PromotionApplyResult {
  className: string;
  promoted: number;
  repeated: number;
  underReview: number;
  graduated: number;
}

function nextClass(className: string): string | null {
  const idx = mock.CLASSES.indexOf(className);
  if (idx < 0) return null;
  return mock.CLASSES[idx + 1] ?? null;
}

export function suggestPromotion(student: Student): PromotionDecision {
  if (student.average >= 60 && student.attendanceRate >= 70) return "promote";
  if (student.average >= 45 && student.attendanceRate >= 50) return "review";
  return "repeat";
}

export async function listPromotionClasses(): Promise<PromotionClassSummary[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/promotion/classes");
  const groups = new Map<string, Student[]>();
  for (const student of mock.students) {
    if (student.status !== "active") continue;
    const list = groups.get(student.className) ?? [];
    list.push(student);
    groups.set(student.className, list);
  }
  const summaries = [...groups.entries()]
    .map(([className, students]) => {
      const counts: Record<PromotionDecision, number> = { promote: 0, repeat: 0, review: 0 };
      for (const student of students) counts[suggestPromotion(student)] += 1;
      return {
        className,
        nextClass: nextClass(className),
        total: students.length,
        promote: counts.promote,
        repeat: counts.repeat,
        review: counts.review,
      };
    })
    .sort((a, b) => a.className.localeCompare(b.className));
  return mockDelay(summaries);
}

export async function getPromotionCandidates(className: string): Promise<PromotionCandidate[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/promotion/classes/${encodeURIComponent(className)}`);
  const candidates = mock.students
    .filter((student) => student.status === "active" && student.className === className)
    .map((student) => ({
      studentId: student.id,
      studentName: `${student.firstName} ${student.lastName}`,
      admissionNumber: student.admissionNumber,
      className: student.className,
      average: student.average,
      attendanceRate: student.attendanceRate,
      suggested: suggestPromotion(student),
    }));
  return mockDelay(candidates);
}

export async function applyPromotion(
  className: string,
  decisions: Record<string, PromotionDecision>,
): Promise<PromotionApplyResult> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/promotion/classes/${encodeURIComponent(className)}/apply`, {
      method: "POST",
      body: { decisions },
    });

  let promoted = 0;
  let repeated = 0;
  let underReview = 0;
  let graduated = 0;

  for (const student of mock.students) {
    if (student.status !== "active" || student.className !== className) continue;
    const decision = decisions[student.id];
    if (!decision) continue;
    const from = student.className;
    if (decision === "promote") {
      const target = nextClass(from);
      if (target) {
        student.className = target;
        student.enrollmentHistory.push({
          session: mock.school.currentSession,
          className: from,
          outcome: "Promoted",
        });
        promoted += 1;
      } else {
        student.status = "graduated";
        student.enrollmentHistory.push({
          session: mock.school.currentSession,
          className: from,
          outcome: "Promoted",
        });
        graduated += 1;
      }
    } else if (decision === "repeat") {
      student.enrollmentHistory.push({
        session: mock.school.currentSession,
        className: from,
        outcome: "Repeated",
      });
      repeated += 1;
    } else {
      student.enrollmentHistory.push({
        session: mock.school.currentSession,
        className: from,
        outcome: "Under review",
      });
      underReview += 1;
    }
  }

  return mockDelay({ className, promoted, repeated, underReview, graduated }, 900);
}
