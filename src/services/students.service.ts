import { apiFetch, type Paginated } from "@/api/client";
import type { Student } from "@/types";

export interface StudentQuery {
  search?: string;
  className?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export async function listStudents(query: StudentQuery = {}): Promise<Paginated<Student>> {
  // SECURITY: Backend must verify permission students.read and schoolId match, or restrict parents and students to authorized linked records.
  return apiFetch("/students", { query: { ...query } });
}

export async function getStudent(id: string): Promise<Student> {
  // SECURITY: Backend must verify permission students.read and schoolId match, or allow only the caller's own or linked student record.
  return apiFetch(`/students/${id}`);
}

export interface StudentStats {
  total: number;
  active: number;
  suspended: number;
  averageAttendance: number;
  outstandingFees: number;
}

export async function getStudentStats(): Promise<StudentStats> {
  // SECURITY: Backend must verify permission students.read and schoolId match before returning school-wide statistics.
  return apiFetch("/students/stats");
}

export interface StudentInput {
  firstName: string;
  lastName: string;
  /**
   * Optional on create: omit it and the server issues the next number for the
   * class and admission year. Required on update, since an admission number is
   * permanent once written.
   */
  admissionNumber?: string;
  gender: "male" | "female";
  dateOfBirth: string;
  className: string;
  arm: string;
  guardianName: string;
  guardianPhone: string;
}

export interface RegistrationOutcome {
  student: Student;
  /** The admission invoice raised at registration, absent when the school has no fee structure yet. */
  invoiceId: string;
  invoiceTotal: string;
  feesConfigured: boolean;
}

export async function createStudent(input: StudentInput): Promise<RegistrationOutcome> {
  // SECURITY: Backend must verify permission students.write and schoolId match.
  // Registration also raises the admission invoice, so the response carries
  // enough for the registrar to tell the family what is owed.
  const { invoiceId, invoiceTotal, feesConfigured, ...student } = await apiFetch<
    Student & { invoiceId?: string; invoiceTotal?: string; feesConfigured?: boolean }
  >("/students", { method: "POST", body: input });
  return {
    student: student as Student,
    invoiceId: invoiceId ?? "",
    invoiceTotal: invoiceTotal ?? "",
    feesConfigured: Boolean(feesConfigured),
  };
}

export async function updateStudent(id: string, input: StudentInput): Promise<Student> {
  // SECURITY: Backend must verify permission students.write and schoolId match.
  // An admission number is permanent once issued, so it must always be present
  // on an update: pass `requireAdmissionNumber` through from the edit form,
  // which prefills the existing value.
  return apiFetch(`/students/${id}`, { method: "PATCH", body: input });
}

export async function suspendStudent(id: string): Promise<Student> {
  // SECURITY: Backend must verify permission students.write and schoolId match.
  return apiFetch(`/students/${id}`, { method: "PATCH", body: { status: "suspended" } });
}

export async function reinstateStudent(id: string): Promise<Student> {
  // SECURITY: Backend must verify permission students.write and schoolId match.
  return apiFetch(`/students/${id}`, { method: "PATCH", body: { status: "active" } });
}

export interface TransferStudentInput {
  studentId: string;
  toSchoolId: string;
}

export async function transferStudent(input: TransferStudentInput): Promise<Student> {
  // SECURITY: Backend must verify permission students.write, match the source student's schoolId, and allow only an approved destination school.
  return apiFetch(`/students/${input.studentId}/transfer`, {
    method: "POST",
    body: { toSchoolId: input.toSchoolId },
  });
}

export interface ImportRow {
  rowNumber: number;
  firstName: string;
  lastName: string;
  admissionNumber: string;
  className: string;
  guardianPhone: string;
  gender: "male" | "female";
  dateOfBirth: string | null;
  arm: string;
  guardianName: string;
  issues: string[];
}

export interface ImportAnalysis {
  fileName: string;
  total: number;
  valid: number;
  duplicates: number;
  missingFields: number;
  rows: ImportRow[];
  capacity: { activeStudents: number; allowed: number; afterImport: number; exceeds: boolean };
}

export async function analyseImportFile(file: File): Promise<ImportAnalysis> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  // SECURITY: Backend must verify permission students.import, derive schoolId from the authenticated user, and perform all CSV validation.
  return apiFetch("/students/import/analyse", { method: "POST", body: formData });
}

export async function commitImport(file: File): Promise<{
  imported: number;
  skipped: number;
  invalid: number;
  duplicates: number;
}> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  // SECURITY: Backend must verify permission students.import, derive schoolId from the authenticated user, and revalidate the file transactionally.
  return apiFetch("/students/import", { method: "POST", body: formData });
}
