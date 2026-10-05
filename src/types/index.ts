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
  /** Amending an already-taken register; distinct from taking it. */
  | "attendance.correct"
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
  avatarUrl: string | null;
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
  enrollmentHistory: EnrollmentHistory[];
}

export interface EnrollmentHistory {
  sessionId: string;
  session: string;
  className: string;
  arm: string;
  status: "not_enrolled" | "active" | "suspended" | "transferred" | "withdrawn" | "completed";
  reviewNote: string;
  flaggedForReview: boolean;
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
  arm?: string;
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
  source?: "admission" | "bulk" | "migration";
  total: number;
  paid: number;
  items: { label: string; amount: number }[];
  status: "unpaid" | "part_paid" | "paid";
}

export interface Payment {
  id: string;
  invoiceId: string;
  studentName: string;
  admissionNumber?: string;
  amount: number;
  method: "cash" | "bank_transfer" | "card" | "pos" | "ussd" | "online";
  status: "pending" | "verified" | "failed" | "refunded" | "reversed" | "cancelled";
  reference: string;
  recordedBy: string;
  createdAt: string;
  invoiceTotal?: number;
  invoicePaid?: number;
}

export interface ResultSheetRow {
  studentId: string;
  studentName: string;
  ca1: number | null;
  ca2: number | null;
  assignment: number | null;
  exam: number | null;
  score: number | null;
  grade: string;
  remark: string;
}

export type ResultSheetStatus =
  "draft" | "submitted" | "under_review" | "approved" | "published" | "locked";

export interface ResultSheetSummary {
  id: string;
  session: string;
  className: string;
  subject: string;
  assessment: string;
  assessmentMax: string;
  term: string;
  status: ResultSheetStatus;
  isLocked: boolean;
  studentCount: number;
  correctionRequested: boolean;
}

export interface ResultSheet extends ResultSheetSummary {
  correctionReason: string;
  rows: ResultSheetRow[];
}

export interface ResultReportEntry {
  studentName: string;
  className: string;
  subject: string;
  term: string;
  ca1: number | null;
  ca2: number | null;
  assignment: number | null;
  exam: number | null;
  score: number | null;
  grade: string;
}

export interface MyPublishedResult extends ResultReportEntry {
  studentId: string;
  session: string;
}

export type NotificationType =
  | "payment"
  | "attendance"
  | "result"
  | "announcement"
  | "subscription"
  | "ai"
  | "security"
  | "system";

export interface Announcement {
  id: string;
  title: string;
  body: string;
  /** Composer labels, already filtered to the ones this audience covers. */
  audience: string[];
  createdAt: string;
  author: string;
  /** A pinned notice stays at the top of the board regardless of its date. */
  isPinned: boolean;
  /** ISO 8601, or null when the notice does not expire. */
  expiresAt: string | null;
  scope: "school" | "platform";
  targetClassId?: string | null;
  targetSectionId?: string | null;
  targetAcademicSessionId?: string | null;
}

export interface AppNotification {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  createdAt: string;
  read: boolean;
  readAt: string | null;
  /** In-app route the notification opens, e.g. "/fees". Empty when none. */
  link: string;
}

/**
 * One page of the feed, plus the unread total.
 *
 * `unread` rides along with every poll because the header badge needs it and
 * splitting it into a second request would double the traffic of the most
 * frequently called endpoint in the app.
 */
export interface NotificationPage {
  results: AppNotification[];
  count: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  unread: number;
}

export interface NotificationPreference {
  type: NotificationType;
  label: string;
  inApp: boolean;
}

export interface LessonPlan {
  id: string;
  subject: string;
  className: string;
  session: string;
  term: string;
  topic: string;
  durationMinutes: number;
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

export interface LessonPlanInput extends Omit<LessonPlan, "id" | "session" | "term" | "updatedAt"> {
  id?: string;
}

/** Monday-first, matching the API and the school calendar. */
export type TimetableWeekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export const TIMETABLE_WEEKDAYS: readonly TimetableWeekday[] = [0, 1, 2, 3, 4, 5, 6];
export const TIMETABLE_WEEKDAY_NAMES: Record<TimetableWeekday, string> = {
  0: "Monday",
  1: "Tuesday",
  2: "Wednesday",
  3: "Thursday",
  4: "Friday",
  5: "Saturday",
  6: "Sunday",
};
export const TIMETABLE_WEEKDAY_SHORT: Record<TimetableWeekday, string> = {
  0: "Mon",
  1: "Tue",
  2: "Wed",
  3: "Thu",
  4: "Fri",
  5: "Sat",
  6: "Sun",
};

/** One bell in the school's day. */
export interface TimetablePeriod {
  id: string;
  name: string;
  /** 24-hour `HH:MM`. */
  startTime: string;
  endTime: string;
  sortOrder: number;
  /** A break is a divider in the grid and cannot hold a lesson. */
  isBreak: boolean;
}

/**
 * One lesson in the weekly timetable.
 *
 * `TimetableSlot` is kept as the loose read shape used by list screens; a
 * `TimetableEntry` is the same lesson with the ids and weekday number the editor
 * needs to address it.
 */
export interface TimetableEntry {
  id: string;
  /** Weekday number, Monday-first. */
  day: number;
  weekday: number;
  dayName: string;
  dayShort: string;
  /** Period label, e.g. "P1". */
  period: string;
  periodId: string;
  classId: string;
  className: string;
  subject: string;
  /** Empty when no teacher is assigned yet. */
  teacher: string;
  teacherId: string;
  /** Empty when no room is booked yet. */
  room: string;
}

export interface TimetableClassOption {
  id: string;
  name: string;
  level: string;
}

export interface TimetableTeacherOption {
  id: string;
  name: string;
}

/** Everything the timetable screen needs in one response. */
export interface TimetableGrid {
  session: string;
  term: string;
  /** Teaching weekdays, derived from the school calendar. */
  days: TimetableWeekday[];
  dayNames: string[];
  dayShortNames: string[];
  periods: TimetablePeriod[];
  entries: TimetableEntry[];
  scope: { classId: string; teacherId: string };
  classes: TimetableClassOption[];
  classIds: Record<string, string>;
  subjects: string[];
  teachers: TimetableTeacherOption[];
  rooms: string[];
}

/** Payload for creating a lesson. Server resolves conflicts on write. */
export interface TimetableEntryInput {
  weekday: number;
  periodId: string;
  classId: string;
  subject: string;
  /** Send an empty string to unassign. */
  teacherId?: string;
  room?: string;
}

export interface TimetablePeriodInput {
  name: string;
  startTime: string;
  endTime: string;
  isBreak?: boolean;
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
