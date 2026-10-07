import { apiFetch, ApiRequestError } from "@/api/client";

export interface ReportCardSubject {
  subject: string;
  ca1: number | null;
  ca2: number | null;
  assignment: number | null;
  exam: number | null;
  total: number;
  grade: string;
}

export interface ReportCardPromotion {
  suggested: "promote" | "conditional" | "repeat" | "review";
  reason: string;
  average: number | null;
  attendanceRate: number | null;
  failedSubjects: number;
  subjectsAssessed: number;
  isFinalClass: boolean;
  nextClass: string | null;
  policy: {
    promoteMinAverage: number;
    promoteMinAttendance: number;
    conditionalMinAverage: number;
    conditionalMinAttendance: number;
    conditionalMaxFailedSubjects: number;
  };
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
  maxScore: number;
  average: number;
  remark: string;
  /** Class position (ties share a rank); `null` when no one is ranked yet. */
  position: { rank: number; outOf: number } | null;
  promotion: ReportCardPromotion | null;
  attendance: {
    recorded: number;
    present: number;
    late: number;
    absent: number;
    excused: number;
    attendanceRate: number;
  };
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
  // SECURITY: Backend must verify permission reports.read and schoolId match, or allow only published own or linked-child reports.
  try {
    return await apiFetch<ReportCard>(`/reports/report-cards/${studentId}`);
  } catch (error) {
    // A 404 is "no report card yet", not a failure: a child whose results are
    // still being marked has nothing to show, and the screens must be able to
    // say exactly that instead of treating the empty response as an error.
    if (error instanceof ApiRequestError && error.status === 404) return null;
    throw error;
  }
}
