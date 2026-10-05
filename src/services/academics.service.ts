import { apiFetch } from "@/api/client";

export interface AcademicStructure {
  session: string;
  /** Id of the school's current `AcademicSession` row, for enrollment-linked calls. */
  sessionId: number | null;
  term: string;
  /** Class names the school actually configured, from `SchoolClass`. */
  classes: string[];
  /** Same classes keyed by name, so callers can address a class by its id. */
  classIds: Record<string, number>;
  /** Sections/arms with their owning class, keyed for targeting. */
  sections: Array<{ id: number; name: string; classId: number }>;
  subjects: string[];
  /** Python weekday numbers that are non-school days: 0 = Monday … 6 = Sunday. */
  attendanceWeekendDays: number[];
  /** ISO dates the school is closed, e.g. public holidays. */
  nonSchoolDays: string[];
}

export const TERM_OPTIONS = ["First Term", "Second Term", "Third Term"];

export async function getAcademicStructure(): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.read and schoolId match.
  return apiFetch("/academics");
}

export async function updateSessionTerm(input: {
  session: string;
  term: string;
}): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch("/academics", { method: "PATCH", body: input });
}

export async function updateSchoolCalendar(input: {
  attendanceWeekendDays?: number[];
  nonSchoolDays?: string[];
}): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  // Only the keys present in `input` are sent, so saving one part of the
  // calendar never clears the other.
  return apiFetch("/academics", { method: "PATCH", body: input });
}

export async function addSubject(name: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch("/academics/subjects", { method: "POST", body: { name } });
}

export async function removeSubject(name: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch(`/academics/subjects/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export async function addClass(name: string, level?: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch("/academics/classes", {
    method: "POST",
    body: { name, ...(level ? { level } : {}) },
  });
}

export async function removeClass(name: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch(`/academics/classes/${encodeURIComponent(name)}`, { method: "DELETE" });
}
