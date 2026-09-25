import { apiFetch } from "@/api/client";

export interface AcademicStructure {
  session: string;
  term: string;
  classes: string[];
  subjects: string[];
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

export async function addSubject(name: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch("/academics/subjects", { method: "POST", body: { name } });
}

export async function removeSubject(name: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch(`/academics/subjects/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export async function addClass(name: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch("/academics/classes", { method: "POST", body: { name } });
}

export async function removeClass(name: string): Promise<AcademicStructure> {
  // SECURITY: Backend must verify permission academics.write and schoolId match.
  return apiFetch(`/academics/classes/${encodeURIComponent(name)}`, { method: "DELETE" });
}
