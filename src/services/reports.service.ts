import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";

export interface ReportCardSubject {
  subject: string;
  ca1: number | null;
  ca2: number | null;
  assignment: number | null;
  exam: number | null;
  total: number;
  grade: string;
}

export interface ReportCard {
  student: {
    id: string;
    name: string;
    admissionNumber: string;
    className: string;
    arm: string;
    gender: string;
    attendanceRate: number;
  };
  school: { name: string; address: string };
  session: string;
  term: string;
  subjects: ReportCardSubject[];
  totalScore: number;
  average: number;
  remark: string;
}

function gradeFor(total: number): string {
  if (total >= 75) return "A";
  if (total >= 60) return "B";
  if (total >= 50) return "C";
  if (total >= 40) return "D";
  return "F";
}

function remarkFor(average: number, attendanceRate: number): string {
  if (average >= 75) {
    return "Outstanding. Keep up the excellent work and continue to help your classmates.";
  }
  if (average >= 60) {
    return "Very good. Consistent effort this term; watch out for careless mistakes in exams.";
  }
  if (average >= 50) {
    return "Good, but there is room for improvement. Revise regularly and attempt more class work.";
  }
  if (average >= 40) {
    return "Fair. More attention is needed in some subjects; cover past questions before exams.";
  }
  return "Unsatisfactory. Please see your class teacher for a study plan for the next term.";
}

/** Builds a termly report card from the student's published result sheets. Sipping unavailable subjects. */
export async function getReportCard(studentId: string): Promise<ReportCard | null> {
  if (!USE_MOCK_ADAPTER) return apiFetch<ReportCard>(`/reports/report-cards/${studentId}`);
  const student = mock.students.find((s) => s.id === studentId);
  if (!student) return null;

  const subjects: ReportCardSubject[] = [];
  for (const sheet of mock.resultSheets) {
    if (sheet.status !== "approved" && sheet.status !== "published") continue;
    const row = sheet.rows.find((r) => r.studentId === studentId);
    if (!row) continue;
    const total = (row.ca1 ?? 0) + (row.ca2 ?? 0) + (row.assignment ?? 0) + (row.exam ?? 0);
    subjects.push({
      subject: sheet.subject,
      ca1: row.ca1,
      ca2: row.ca2,
      assignment: row.assignment,
      exam: row.exam,
      total,
      grade: gradeFor(total),
    });
  }

  if (subjects.length === 0) return null;

  const totalScore = subjects.reduce((sum, s) => sum + s.total, 0);
  const average = Math.round(totalScore / subjects.length);
  const attendanceRate = student.attendanceRate;

  return {
    student: {
      id: student.id,
      name: `${student.firstName} ${student.lastName}`,
      admissionNumber: student.admissionNumber,
      className: student.className,
      arm: student.arm,
      gender: student.gender,
      attendanceRate,
    },
    school: { name: mock.school.name, address: `${mock.school.address}, ${mock.school.state}` },
    session: mock.school.currentSession,
    term: mock.school.currentTerm,
    subjects,
    totalScore,
    average,
    remark: remarkFor(average, attendanceRate),
  };
}
