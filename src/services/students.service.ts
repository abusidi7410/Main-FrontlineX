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
  return apiFetch("/students", { query: { ...query } });
}

export async function getStudent(id: string): Promise<Student> {
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
  return apiFetch("/students/stats");
}

export interface StudentInput {
  firstName: string;
  lastName: string;
  admissionNumber: string;
  gender: "male" | "female";
  dateOfBirth: string;
  className: string;
  arm: string;
  guardianName: string;
  guardianPhone: string;
}

export async function createStudent(input: StudentInput): Promise<Student> {
  return apiFetch("/students", { method: "POST", body: input });
}

export async function updateStudent(id: string, input: StudentInput): Promise<Student> {
  return apiFetch(`/students/${id}`, { method: "PATCH", body: input });
}

export async function suspendStudent(id: string): Promise<Student> {
  return apiFetch(`/students/${id}`, { method: "PATCH", body: { status: "suspended" } });
}

export async function reinstateStudent(id: string): Promise<Student> {
  return apiFetch(`/students/${id}`, { method: "PATCH", body: { status: "active" } });
}

export interface TransferStudentInput {
  studentId: string;
  toSchoolId: string;
}

export async function transferStudent(input: TransferStudentInput): Promise<Student> {
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

/** Parses a CSV in the browser then validates it exactly like the API will. */
export async function analyseImportFile(
  file: File,
  activeStudents: number,
  allowed: number,
): Promise<ImportAnalysis> {
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  const [header = "", ...body] = lines;
  const cols = header.split(",").map((c) => c.trim().toLowerCase());
  const idx = (name: string) => cols.indexOf(name);
  const existing = await apiFetch<Paginated<Student>>("/students", { query: { pageSize: 1000 } });
  const seen = new Set(existing.results.map((s) => s.admissionNumber.toLowerCase()));
  let duplicates = 0;
  let missingFields = 0;

  const rows: ImportRow[] = body.map((line, i) => {
    const cells = line.split(",").map((c) => c.trim());
    const row: ImportRow = {
      rowNumber: i + 2,
      firstName: cells[idx("first_name")] ?? "",
      lastName: cells[idx("last_name")] ?? "",
      admissionNumber: cells[idx("admission_number")] ?? "",
      className: cells[idx("class")] ?? "",
      guardianPhone: cells[idx("guardian_phone")] ?? "",
      issues: [],
    };
    if (!row.firstName || !row.lastName || !row.className) {
      row.issues.push("Missing required field");
      missingFields += 1;
    }
    const key = row.admissionNumber.toLowerCase();
    if (!key) {
      row.issues.push("Missing admission number");
      missingFields += 1;
    } else if (seen.has(key)) {
      row.issues.push("Duplicate admission number");
      duplicates += 1;
    } else {
      seen.add(key);
    }
    return row;
  });

  const valid = rows.filter((r) => r.issues.length === 0).length;
  return {
    fileName: file.name,
    total: rows.length,
    valid,
    duplicates,
    missingFields,
    rows,
    capacity: {
      activeStudents,
      allowed,
      afterImport: activeStudents + valid,
      exceeds: activeStudents + valid > allowed,
    },
  };
}

export async function commitImport(analysis: ImportAnalysis): Promise<{ imported: number }> {
  return apiFetch("/students/import", { method: "POST", body: { rows: analysis.rows } });
}