import { apiFetch } from "@/api/client";
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

export function suggestPromotion(student: Student): PromotionDecision {
  if (student.average >= 60 && student.attendanceRate >= 70) return "promote";
  if (student.average >= 45 && student.attendanceRate >= 50) return "review";
  return "repeat";
}

export async function listPromotionClasses(): Promise<PromotionClassSummary[]> {
  return apiFetch("/promotion/classes");
}

export async function getPromotionCandidates(className: string): Promise<PromotionCandidate[]> {
  return apiFetch(`/promotion/classes/${encodeURIComponent(className)}`);
}

export async function applyPromotion(
  className: string,
  decisions: Record<string, PromotionDecision>,
): Promise<PromotionApplyResult> {
  return apiFetch(`/promotion/classes/${encodeURIComponent(className)}/apply`, {
    method: "POST",
    body: { decisions },
  });
}