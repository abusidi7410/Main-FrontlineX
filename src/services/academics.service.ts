import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";

export interface AcademicStructure {
  session: string;
  term: string;
  classes: string[];
  subjects: string[];
}

export const TERM_OPTIONS = ["First Term", "Second Term", "Third Term"];

function snapshot(): AcademicStructure {
  return {
    session: mock.school.currentSession,
    term: mock.school.currentTerm,
    classes: [...mock.CLASSES],
    subjects: [...mock.SUBJECTS],
  };
}

export async function getAcademicStructure(): Promise<AcademicStructure> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/academics");
  return mockDelay(snapshot(), 300);
}

export async function updateSessionTerm(input: {
  session: string;
  term: string;
}): Promise<AcademicStructure> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/academics", { method: "PATCH", body: input });
  mock.school.currentSession = input.session.trim();
  mock.school.currentTerm = input.term;
  return mockDelay(snapshot(), 550);
}

export async function addSubject(name: string): Promise<AcademicStructure> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/academics/subjects", { method: "POST", body: { name } });
  const trimmed = name.trim();
  if (!mock.SUBJECTS.some((s) => s.toLowerCase() === trimmed.toLowerCase())) {
    mock.SUBJECTS.push(trimmed);
  }
  return mockDelay(snapshot(), 400);
}

export async function removeSubject(name: string): Promise<AcademicStructure> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/academics/subjects/${encodeURIComponent(name)}`, { method: "DELETE" });
  const index = mock.SUBJECTS.findIndex((s) => s === name);
  if (index >= 0) mock.SUBJECTS.splice(index, 1);
  return mockDelay(snapshot(), 400);
}

export async function addClass(name: string): Promise<AcademicStructure> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/academics/classes", { method: "POST", body: { name } });
  const trimmed = name.trim();
  if (!mock.CLASSES.some((c) => c.toLowerCase() === trimmed.toLowerCase())) {
    mock.CLASSES.push(trimmed);
  }
  return mockDelay(snapshot(), 400);
}

export async function removeClass(name: string): Promise<AcademicStructure> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/academics/classes/${encodeURIComponent(name)}`, { method: "DELETE" });
  const index = mock.CLASSES.findIndex((c) => c === name);
  if (index >= 0) mock.CLASSES.splice(index, 1);
  return mockDelay(snapshot(), 400);
}
