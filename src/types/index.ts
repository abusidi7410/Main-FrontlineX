export type Role =
  | "platform_manager"
  | "school_admin"
  | "principal"
  | "teacher"
  | "accountant"
  | "secretary"
  | "parent"
  | "student";

export type Permission =
  | "students.read"
  | "students.write"
  | "students.register"
  | "students.approve"
  | "students.import"
  | "enrollment.manage"
  | "staff.read"
  | "staff.write"
  | "accounts.read"
  | "accounts.write"
  | "academics.read"
  | "academics.write"
  | "attendance.read"
  | "attendance.write"
  | "results.read"
  | "results.write"
  | "results.approve"
  | "results.publish"
  | "finance.read"
  | "finance.write"
  | "finance.verify"
  | "finance.structure"
  | "finance.invoice"
  | "finance.payment"
  | "timetable.read"
  | "timetable.write"
  | "lessonplans.read"
  | "lessonplans.write"
  | "communication.read"
  | "communication.write"
  | "reports.read"
  | "subscription.read"
  | "subscription.write"
  | "settings.read"
  | "settings.write"
  | "audit.read"
  | "ai.teaching"
  | "ai.academic"
  | "ai.finance"
  | "ai.platform"
  | "ai.parent"
  | "ai.student"
  | "platform.manage";

export interface AuthUser {
  id: string;
  fullName: string;
  email: string;
  phone: string;
  role: Role;
  permissions: Permission[];
  schoolId: string | null;
  avatarUrl?: string;
}

export type SchoolStatus = "pending_payment" | "active" | "grace" | "suspended" | "trial";

export interface School {
  id: string;
  name: string;
  slug: string;
  logoUrl?: string;
  status: SchoolStatus;
  address: string;
  state: string;
  lga: string;
  phone: string;
  email: string;
  currentSession: string;
  currentTerm: string;
  branding: { primary: string; secondary: string };
  studentCount: number;
  staffCount: number;
}

export interface SubscriptionTier {
  id: string;
  label: string;
  minStudents: number;
  maxStudents: number | null;
  monthlyPrice: number;
  aiCredits: number;
  storageGb: number;
  smsAllowance: number;
  features: string[];
}

export interface SubscriptionState {
  tierId: string;
  status: SchoolStatus;
  activeStudents: number;
  growthAllowance: number;
  renewalDate: string;
  aiCreditsUsed: number;
  aiCreditsTotal: number;
  storageUsedGb: number;
  paymentMethod: string | null;
}

export interface Student {
  id: string;
  admissionNumber: string;
  firstName: string;
  lastName: string;
  gender: "male" | "female";
  dateOfBirth: string;
  className: string;
  arm: string;
  status: "active" | "pending_payment" | "suspended" | "graduated" | "withdrawn" | "transferred";
  guardianName: string;
  guardianPhone: string;
  photoUrl?: string;
  transferredTo?: { schoolId: string; schoolName: string; transferredAt: string } | undefined;
  attendanceRate: number;
  average: number;
  outstandingFees: number;
  enrollmentHistory: { session: string; className: string; outcome: string }[];
}

export interface StaffMember {
  id: string;
  fullName: string;
  email: string;
  phone: string;
  role: Role;
  subjects: string[];
  classes: string[];
  status: "active" | "invited" | "suspended";
}

export interface SchoolAccount {
  id: string;
  fullName: string;
  email: string;
  phone: string;
  role: Role;
  status: "active" | "inactive";
  mustChangePassword: boolean;
  lastLogin: string | null;
  joinedAt: string;
  student?: {
    id: string;
    name: string;
    admissionNumber: string;
    className: string;
  } | null;
  staff?: { id: string; fullName: string; role: string } | null;
}

export interface DefaultCredentials {
  email: string;
  password: string;
  mustChangePassword: true;
}

export interface AccountCreateInput {
  fullName: string;
  email: string;
  phone?: string;
  role: Role;
  password?: string;
  studentId?: string;
  staffId?: string;
}

export interface AccountStats {
  total: number;
  active: number;
  byRole: Record<
    Role,
    {
      total: number;
      active: number;
    }
  >;
}

export type AttendanceStatus = "present" | "absent" | "late" | "excused";

export interface AttendanceRecord {
  studentId: string;
  status: AttendanceStatus;
}

export interface AttendanceSubmission {
  id: string;
  className: string;
  date: string;
  subject?: string;
  records: AttendanceRecord[];
  syncState: "pending" | "synced" | "failed";
  updatedAt: number;
}

export interface Invoice {
  id: string;
  studentId: string;
  studentName: string;
  className: string;
  term: string;
  total: number;
  paid: number;
  items: { label: string; amount: number }[];
  status: "unpaid" | "part_paid" | "paid";
}

export interface Payment {
  id: string;
  invoiceId: string;
  studentName: string;
  amount: number;
  method: "cash" | "bank_transfer" | "card" | "pos" | "ussd" | "online";
  status: "pending" | "verified" | "failed" | "refunded" | "reversed" | "cancelled";
  reference: string;
  recordedBy: string;
  createdAt: string;
}

export interface ResultSheetRow {
  studentId: string;
  studentName: string;
  ca1: number | null;
  ca2: number | null;
  assignment: number | null;
  exam: number | null;
}

export interface ResultSheet {
  id: string;
  className: string;
  subject: string;
  term: string;
  status: "draft" | "submitted" | "under_review" | "approved" | "published";
  rows: ResultSheetRow[];
}

export interface Announcement {
  id: string;
  title: string;
  body: string;
  audience: string[];
  createdAt: string;
  author: string;
}

export interface AppNotification {
  id: string;
  type:
    | "payment"
    | "attendance"
    | "result"
    | "announcement"
    | "subscription"
    | "ai"
    | "security"
    | "system";
  title: string;
  body: string;
  createdAt: string;
  read: boolean;
}

export interface LessonPlan {
  id: string;
  subject: string;
  className: string;
  topic: string;
  duration: string;
  objectives: string;
  previousKnowledge: string;
  introduction: string;
  teacherActivities: string;
  studentActivities: string;
  materials: string;
  assessment: string;
  homework: string;
  updatedAt: string;
}

export interface TimetableSlot {
  id: string;
  day: string;
  period: string;
  className: string;
  subject: string;
  teacher: string;
  room: string;
}

export interface PlatformSchool {
  id: string;
  name: string;
  state: string;
  students: number;
  tierId: string;
  status: SchoolStatus;
  mrr: number;
  createdAt: string;
}

export interface AtRiskSchool {
  id: string;
  name: string;
  state: string;
  plan: string;
  students: number;
  lastActive: string | null;
  renewalDate: string | null;
  status: SchoolStatus;
  mrr: number;
  failedPayments: number;
}

export type PlatformOverviewRange = "7d" | "30d" | "90d";

export interface PlatformOverview {
  mrr: number;
  mrrTrend: number[];
  schoolsByStatus: Record<SchoolStatus, number>;
  activeSchools: number;
  activeSchoolsTrend: number[];
  activeSchoolsGrowth: number;
  activeLogins24h: number;
  failedPayments: number;
  upcomingRenewals: number;
  atRiskSchools: AtRiskSchool[];
  rangeDays: number;
}

export interface ApiError {
  message: string;
  code?: string;
  fieldErrors?: Record<string, string>;
}

export interface AuditEvent {
  id: string;
  actor: string;
  role: Role;
  action: string;
  detail: string;
  ip: string;
  createdAt: string;
}

export interface UssdCommand {
  code: string;
  description: string;
}

export interface UssdConfig {
  enabled: boolean;
  shortCode: string;
  fullCode: string;
  commands: UssdCommand[];
}
