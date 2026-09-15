import { apiFetch } from "@/api/client";

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
  return apiFetch<ReportCard>(`/reports/report-cards/${studentId}`);
}