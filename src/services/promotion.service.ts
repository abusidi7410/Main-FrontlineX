import { apiFetch } from "@/api/client";

export type PromotionDecision = "promote" | "conditional" | "repeat" | "review";

export interface PromotionPolicy {
  promoteMinAverage: number;
  promoteMinAttendance: number;
  conditionalMinAverage: number;
  conditionalMinAttendance: number;
  conditionalMaxFailedSubjects: number;
}

export interface PromotionCandidate {
  studentId: string;
  studentName: string;
  admissionNumber: string;
  className: string;
  average: number | null;
  attendanceRate: number | null;
  attendanceRecords: number;
  subjectsAssessed: number;
  failedSubjects: number;
  incomplete: boolean;
  reason: string;
  isFinalClass: boolean;
  suggested: PromotionDecision;
}

export interface PromotionClassSummary {
  className: string;
  nextClass: string | null;
  total: number;
  promote: number;
  conditional: number;
  repeat: number;
  review: number;
  graduated: number;
}

export interface PromotionOverview {
  sourceSession: string;
  targetSession: string;
  policy: PromotionPolicy;
  classes: PromotionClassSummary[];
}

export interface PromotionClassCandidates {
  className: string;
  nextClass: string | null;
  sourceSession: string;
  targetSession: string;
  policy: PromotionPolicy;
  candidates: PromotionCandidate[];
}

export interface PromotionApplyResult {
  className: string;
  sourceSession: string;
  targetSession: string;
  promoted: number;
  conditional: number;
  repeated: number;
  underReview: number;
  graduated: number;
}

export async function listPromotionClasses(): Promise<PromotionOverview> {
  return apiFetch("/promotion/classes");
}

export async function getPromotionCandidates(className: string): Promise<PromotionClassCandidates> {
  return apiFetch(`/promotion/classes/${encodeURIComponent(className)}`);
}

export async function getPromotionPolicy(): Promise<PromotionPolicy> {
  return apiFetch("/promotion/policy");
}

export async function updatePromotionPolicy(policy: PromotionPolicy): Promise<PromotionPolicy> {
  return apiFetch("/promotion/policy", { method: "PATCH", body: policy });
}

export async function applyPromotion(
  className: string,
  decisions: Record<string, PromotionDecision>,
): Promise<PromotionApplyResult> {
  // SECURITY: Backend must verify permission students.write and schoolId match for the class and every decision student.
  return apiFetch(`/promotion/classes/${encodeURIComponent(className)}/apply`, {
    method: "POST",
    body: { decisions },
  });
}
