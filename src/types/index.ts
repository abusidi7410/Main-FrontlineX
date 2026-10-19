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
  /** Staff check-in: the caller's own GPS check-in and their own records. */
  | "attendance.staff"
  /** See every staff check-in and resolve uncertain ones. */
  | "attendance.staff.manage"
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
  | "admissions.read"
  | "admissions.write"
  | "admissions.review"
  | "admissions.settings"
  | "receipts.read"
  | "receipts.issue"
  | "receipts.reprint"
  | "receipts.void"
  | "receipts.settings"
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
  email: string | null;
  phone: string;
  role: Role;
  permissions: Permission[];
  schoolId: string | null;
  avatarUrl: string | null;
  mustChangePassword: boolean;
  /** The teacher's staff record id, so the register can default to their own
      class. `null` for accounts with no linked staff record (admins, parents). */
  staffId: string | null;
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
  /** Campus coordinates captured at registration or in Settings; null until set. */
  latitude: number | null;
  longitude: number | null;
  gpsAccuracy: number | null;
  /** How far (metres) a staff check-in may be from the campus. */
  attendanceRadius: number;
  timezone: string;
  locationSetAt: string | null;
  locationConfirmedAt: string | null;
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
  /** Raw backend subscription state (active/pending/trial/…): tells the UI
      whether payment is still required without guessing from dates. */
  subscriptionStatus?: string | undefined;
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
  /** How the dialog links a student account: lookup by admission number. */
  admissionNumber?: string;
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

export type StaffAttendanceStatus = "at_school" | "outside" | "unverified" | "pending_review";

export interface StaffAttendanceCheckInInput {
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
  notes?: string;
  /** Only used by the offline queue: the day the check-in was captured. */
  date?: string;
}

export interface StaffAttendanceRecord {
  id: string;
  staffId: string;
  staffName: string;
  role: string;
  date: string;
  checkInAt: string;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  distanceMeters: number | null;
  status: StaffAttendanceStatus;
  notes: string;
  reviewedBy: string;
  reviewedAt: string | null;
  reviewNote: string;
}

export interface StaffAttendancePage {
  records: StaffAttendanceRecord[];
  count: number;
  page: number;
  pageSize: number;
  totalPages: number;
  staffId: string | null;
}

export interface ReverseGeocodeResult {
  label: string;
  address: Record<string, string>;
  latitude: number;
  longitude: number;
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
  failedPayments: number;
}

export type PlatformOverviewRange = "7d" | "30d" | "90d";

export interface PlatformOverview {
  walletDepositsTrend: number[];
  walletDepositsTotal: number;
  activationChargesTrend: number[];
  activationChargesTotal: number;
  smsChargesTrend: number[];
  smsChargesTotal: number;
  refundsTrend: number[];
  refundsTotal: number;
  totalUsers: number;
  totalStudents: number;
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

export type AdmissionStatus =
  "draft" | "submitted" | "under_review" | "approved" | "rejected" | "withdrawn";

export type AdmissionApplicantType = "new" | "transfer" | "returning";

export type AdmissionDocumentStatus = "pending" | "verified" | "rejected";

/**
 * Mirrors `AdmissionDocument.Category` in `backend/admissions/models.py`. The
 * server validates `requiredDocuments` against exactly this vocabulary, so the
 * settings screen must offer no category that the API would reject.
 */
export const ADMISSION_DOCUMENT_CATEGORIES = [
  "birth_certificate",
  "passport_photo",
  "previous_report",
  "transfer_certificate",
  "immunization",
  "other",
] as const;

export type AdmissionDocumentCategory = (typeof ADMISSION_DOCUMENT_CATEGORIES)[number];

export const ADMISSION_DOCUMENT_LABELS: Record<AdmissionDocumentCategory, string> = {
  birth_certificate: "Birth certificate",
  passport_photo: "Passport photograph",
  previous_report: "Previous school report",
  transfer_certificate: "Transfer certificate",
  immunization: "Immunization record",
  other: "Other supporting document",
};

export interface AdmissionDocument {
  id: string;
  category: AdmissionDocumentCategory;
  categoryLabel: string;
  originalFilename: string;
  contentType: string;
  sizeBytes: number;
  status: AdmissionDocumentStatus;
  uploadedAt: string;
  uploadedBy: string;
  reviewedBy: string;
  reviewedAt: string | null;
  reviewNote: string;
  downloadUrl: string;
  applicationId: string | null;
  studentId: string | null;
}

export interface AdmissionApplication {
  id: string;
  status: AdmissionStatus;
  applicantType: AdmissionApplicantType;
  firstName: string;
  middleName: string;
  lastName: string;
  gender: "" | "male" | "female";
  dateOfBirth: string | null;
  nationality: string;
  stateOfOrigin: string;
  lgaOfOrigin: string;
  religion: string;
  classId: number | null;
  className: string;
  levelCode: string;
  academicSessionId: number | null;
  academicSession: string;
  admissionYear: number | null;
  guardianName: string;
  guardianRelationship: string;
  guardianPhone: string;
  guardianEmail: string;
  guardianOccupation: string;
  guardianAddress: string;
  secondGuardianName: string;
  secondGuardianPhone: string;
  bloodGroup: string;
  allergies: string;
  medicalConditions: string;
  emergencyContactName: string;
  emergencyContactPhone: string;
  previousSchoolName: string;
  previousSchoolAddress: string;
  lastClassCompleted: string;
  reasonForTransfer: string;
  refereeName: string;
  refereePhone: string;
  refereeAddress: string;
  sponsorName: string;
  sponsorRelationship: string;
  sponsorPhone: string;
  sponsorEmail: string;
  sponsorAddress: string;
  mailingAddress: string;
  declaredBy: string;
  declaredAt: string | null;
  submittedAt: string | null;
  reviewedBy: string;
  reviewedAt: string | null;
  decisionReason: string;
  admissionNumber: string;
  studentId: string | null;
  duplicateOf: string | null;
  requiredDocuments: AdmissionDocumentCategory[];
  missingDocuments: AdmissionDocumentCategory[];
  createdBy: string;
  createdAt: string;
  lastSavedAt: string;
  /** Present on the detail endpoint only. */
  documents?: AdmissionDocument[];
}

export type AdmissionApplicationInput = Partial<
  Omit<
    AdmissionApplication,
    | "id"
    | "status"
    | "className"
    | "levelCode"
    | "academicSession"
    | "declaredAt"
    | "submittedAt"
    | "reviewedBy"
    | "reviewedAt"
    | "decisionReason"
    | "admissionNumber"
    | "studentId"
    | "duplicateOf"
    | "requiredDocuments"
    | "missingDocuments"
    | "createdBy"
    | "createdAt"
    | "lastSavedAt"
    | "documents"
  >
>;

export interface AdmissionSettings {
  requiredDocuments: AdmissionDocumentCategory[];
  refereeRequired: boolean;
  sponsorEnabled: boolean;
  requirePreviousSchoolForTransfer: boolean;
  declarationText: string;
}

export interface AdmissionStats {
  total: number;
  draft: number;
  submitted: number;
  underReview: number;
  approved: number;
  rejected: number;
  withdrawn: number;
  needsReview: number;
  approvedThisMonth: number;
}

export interface AdmissionAccess {
  amountKobo: number;
  periodStart: string;
  periodEnd: string;
  walletBalanceKobo: number;
}

export interface AdmissionApprovalResult extends AdmissionApplication {
  studentId: string;
  invoiceId: string;
  invoiceTotal: string;
  registrationFeeConfigured: boolean;
  access: AdmissionAccess | null;
}

export type ReceiptStatus = "issued" | "voided";

export interface Receipt {
  id: string;
  receiptNumber: string;
  status: ReceiptStatus;
  paymentId: string;
  payerName: string;
  amount: string;
  amountInWords: string;
  purpose: string;
  balanceAfter: string;
  issuedBy: string;
  issuedAt: string;
  reprintCount: number;
  lastReprintedAt: string | null;
  voidedBy: string;
  voidedAt: string | null;
  voidReason: string;
  replacesId: string | null;
  school: Record<string, unknown>;
  student: Record<string, unknown>;
  invoice: Record<string, unknown>;
  payment: Record<string, unknown>;
  studentName: string;
  admissionNumber: string;
  downloadUrl: string;
}

export interface ReceiptSettings {
  prefix: string;
  footerNote: string;
  paperSize: "A5" | "A4";
  showLogo: boolean;
}

export interface ReceiptStats {
  totalIssued: number;
  totalVoided: number;
  issuedThisMonth: number;
  valueThisMonth: string;
  recent: Receipt[];
}
