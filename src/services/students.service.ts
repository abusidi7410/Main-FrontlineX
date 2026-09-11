import { USE_MOCK_ADAPTER, apiFetch, mockDelay, type Paginated } from "@/api/client";
import * as mock from "@/api/mock";
import type { Student } from "@/types";

export interface StudentQuery {
  search?: string;
  className?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export async function listStudents(query: StudentQuery = {}): Promise<Paginated<Student>> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/students", { query: { ...query } });
  const { search = "", className = "", status = "", page = 1, pageSize = 10 } = query;
  const term = search.trim().toLowerCase();
  const filtered = mock.students.filter((s) => {
    const matchesSearch =
      !term ||
      `${s.firstName} ${s.lastName}`.toLowerCase().includes(term) ||
      s.admissionNumber.toLowerCase().includes(term) ||
      s.guardianName.toLowerCase().includes(term);
    const matchesClass = !className || s.className === className;
    const matchesStatus = !status || s.status === status;
    return matchesSearch && matchesClass && matchesStatus;
  });
  return mockDelay({
    results: filtered.slice((page - 1) * pageSize, page * pageSize),
    count: filtered.length,
    page,
    pageSize,
  });
}

export async function getStudent(id: string): Promise<Student> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/students/${id}`);
  const found = mock.students.find((s) => s.id === id);
  if (!found) throw new Error("We couldn't find that student record.");
  return mockDelay(found, 350);
}

export interface StudentStats {
  total: number;
  active: number;
  suspended: number;
  averageAttendance: number;
  outstandingFees: number;
}

export async function getStudentStats(): Promise<StudentStats> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/students/stats");
  const all = mock.students;
  const total = all.length;
  const averageAttendance =
    total > 0 ? Math.round(all.reduce((sum, s) => sum + s.attendanceRate, 0) / total) : 0;
  return mockDelay(
    {
      total,
      active: all.filter((s) => s.status === "active").length,
      suspended: all.filter((s) => s.status === "suspended").length,
      averageAttendance,
      outstandingFees: all.reduce((sum, s) => sum + s.outstandingFees, 0),
    },
    300,
  );
}

function findStudent(id: string): Student {
  const found = mock.students.find((s) => s.id === id);
  if (!found) throw new Error("We couldn't find that student record.");
  return found;
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
  if (!USE_MOCK_ADAPTER) return apiFetch("/students", { method: "POST", body: input });
  const created: Student = {
    ...input,
    id: `stu_${Date.now()}`,
    status: "active",
    attendanceRate: 100,
    average: 0,
    outstandingFees: 0,
    enrollmentHistory: [
      { session: mock.school.currentSession, className: input.className, outcome: "In progress" },
    ],
  };
  mock.students.unshift(created);
  return mockDelay(created, 650);
}

export async function updateStudent(id: string, input: StudentInput): Promise<Student> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/students/${id}`, { method: "PATCH", body: input });
  const student = findStudent(id);
  Object.assign(student, {
    firstName: input.firstName,
    lastName: input.lastName,
    admissionNumber: input.admissionNumber,
    gender: input.gender,
    dateOfBirth: input.dateOfBirth,
    className: input.className,
    arm: input.arm,
    guardianName: input.guardianName,
    guardianPhone: input.guardianPhone,
  });
  return mockDelay(student, 650);
}

export async function suspendStudent(id: string): Promise<Student> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/students/${id}`, { method: "PATCH", body: { status: "suspended" } });
  const student = findStudent(id);
  student.status = "suspended";
  return mockDelay(student, 500);
}

export async function reinstateStudent(id: string): Promise<Student> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/students/${id}`, { method: "PATCH", body: { status: "active" } });
  const student = findStudent(id);
  student.status = "active";
  return mockDelay(student, 500);
}

export interface TransferStudentInput {
  studentId: string;
  toSchoolId: string;
}

export async function transferStudent(input: TransferStudentInput): Promise<Student> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/students/${input.studentId}/transfer`, {
      method: "POST",
      body: { toSchoolId: input.toSchoolId },
    });
  const student = findStudent(input.studentId);
  const target = mock.platformSchools.find((s) => s.id === input.toSchoolId);
  if (!target) throw new Error("We couldn't find the destination school.");
  student.status = "transferred";
  student.transferredTo = {
    schoolId: target.id,
    schoolName: target.name,
    transferredAt: new Date().toISOString(),
  };
  student.enrollmentHistory = [
    ...student.enrollmentHistory,
    {
      session: mock.school.currentSession,
      className: student.className,
      outcome: `Transferred to ${target.name}`,
    },
  ];
  return mockDelay(student, 700);
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
  const seen = new Set(mock.students.map((s) => s.admissionNumber.toLowerCase()));
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
  if (!USE_MOCK_ADAPTER)
    return apiFetch("/students/import", { method: "POST", body: { rows: analysis.rows } });
  const valid = analysis.rows.filter((r) => r.issues.length === 0);
  valid.forEach((r) => {
    mock.students.unshift({
      id: `stu_${Date.now()}_${r.rowNumber}`,
      admissionNumber: r.admissionNumber,
      firstName: r.firstName,
      lastName: r.lastName,
      gender: "male",
      dateOfBirth: "2013-01-01",
      className: r.className,
      arm: "A",
      status: "active",
      guardianName: "—",
      guardianPhone: r.guardianPhone,
      attendanceRate: 100,
      average: 0,
      outstandingFees: 0,
      enrollmentHistory: [
        { session: mock.school.currentSession, className: r.className, outcome: "In progress" },
      ],
    });
  });
  return mockDelay({ imported: valid.length }, 1200);
}
