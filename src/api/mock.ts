import type {
  Announcement,
  AppNotification,
  AttendanceStatus,
  Invoice,
  LessonPlan,
  Payment,
  PlatformSchool,
  ResultSheet,
  School,
  StaffMember,
  Student,
  SubscriptionState,
  TimetableSlot,
} from "@/types";

const FIRST_NAMES = [
  "Ahmed",
  "Aisha",
  "Musa",
  "Fatima",
  "Chinedu",
  "Ngozi",
  "Ibrahim",
  "Zainab",
  "Emeka",
  "Blessing",
  "Yusuf",
  "Halima",
  "Tunde",
  "Amina",
  "Obinna",
  "Grace",
  "Sadiq",
  "Kemi",
  "Suleiman",
  "Chiamaka",
];
const LAST_NAMES = [
  "Abubakar",
  "Okafor",
  "Bello",
  "Adeyemi",
  "Nwosu",
  "Ibrahim",
  "Eze",
  "Danjuma",
  "Balogun",
  "Uche",
  "Sani",
  "Adewale",
];
export const CLASSES = [
  "Nursery 1",
  "Nursery 2",
  "Primary 1",
  "Primary 2",
  "Primary 3",
  "Primary 4",
  "Primary 5",
  "Primary 6",
  "JSS 1",
  "JSS 2",
  "JSS 3",
  "SS 1",
  "SS 2",
  "SS 3",
];
export const ARMS = ["A", "B", "C"];
export const SUBJECTS = [
  "Mathematics",
  "English Language",
  "Basic Science",
  "Social Studies",
  "Civic Education",
  "Computer Studies",
  "Agricultural Science",
  "Business Studies",
];
export const STATES = [
  "Kano",
  "Lagos",
  "Kaduna",
  "Rivers",
  "Oyo",
  "FCT Abuja",
  "Enugu",
  "Sokoto",
  "Borno",
  "Anambra",
];

function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}
const rnd = seeded(20260818);
const pick = <T>(list: T[]) => list[Math.floor(rnd() * list.length)]!;

export const school: School = {
  id: "sch_alnoor",
  name: "Al-Noor Model Academy",
  slug: "al-noor",
  status: "active",
  address: "12 Zaria Road, Nassarawa",
  state: "Kano",
  lga: "Nassarawa",
  phone: "+2348031234567",
  email: "admin@alnoor.edu.ng",
  currentSession: "2025/2026",
  currentTerm: "First Term",
  branding: { primary: "#2563eb", secondary: "#0f172a" },
  studentCount: 523,
  staffCount: 48,
};

export const students: Student[] = Array.from({ length: 240 }, (_, i) => {
  const firstName = pick(FIRST_NAMES);
  const lastName = pick(LAST_NAMES);
  const className = pick(CLASSES);
  const attendanceRate = Math.round(60 + rnd() * 40);
  return {
    id: `stu_${1000 + i}`,
    admissionNumber: `ALN/2025/${String(1000 + i)}`,
    firstName,
    lastName,
    gender: rnd() > 0.5 ? "male" : "female",
    dateOfBirth: `20${String(10 + Math.floor(rnd() * 8)).padStart(2, "0")}-0${1 + Math.floor(rnd() * 9)}-1${Math.floor(rnd() * 9)}`,
    className,
    arm: pick(ARMS),
    status: "active",
    guardianName: `${rnd() > 0.5 ? "Mr." : "Mrs."} ${lastName}`,
    guardianPhone: `+23480${Math.floor(10000000 + rnd() * 89999999)}`,
    attendanceRate,
    average: Math.round(40 + rnd() * 55),
    outstandingFees: [0, 0, 15000, 25000, 45000, 60000][Math.floor(rnd() * 6)]!,
    enrollmentHistory: [
      { session: "2023/2024", className: "JSS 1", outcome: "Promoted" },
      { session: "2024/2025", className: "JSS 2", outcome: "Promoted" },
      { session: "2025/2026", className, outcome: "In progress" },
    ],
  } satisfies Student;
});

export const staff: StaffMember[] = Array.from({ length: 48 }, (_, i) => {
  const fullName = `${pick(FIRST_NAMES)} ${pick(LAST_NAMES)}`;
  const role = (["teacher", "teacher", "teacher", "accountant", "secretary", "principal"] as const)[
    i % 6
  ]!;
  return {
    id: `stf_${200 + i}`,
    fullName,
    email: `${fullName.toLowerCase().replace(/\s+/g, ".")}@alnoor.edu.ng`,
    phone: `+23480${Math.floor(10000000 + rnd() * 89999999)}`,
    role,
    subjects: role === "teacher" ? [pick(SUBJECTS), pick(SUBJECTS)] : [],
    classes: role === "teacher" ? [`${pick(CLASSES)}${pick(ARMS)}`] : [],
    status: i % 11 === 0 ? "invited" : "active",
  } satisfies StaffMember;
});

export const subscription: SubscriptionState = {
  tierId: "t600",
  status: "active",
  activeStudents: 523,
  growthAllowance: 45,
  renewalDate: "2026-09-01",
  aiCreditsUsed: 1842,
  aiCreditsTotal: 2500,
  storageUsedGb: 11.4,
  paymentMethod: "Paystack •••• 4291",
};

export const invoices: Invoice[] = students.slice(0, 60).map((s, i) => {
  const items = [
    { label: "Tuition", amount: 60000 },
    { label: "Books", amount: 12000 },
    { label: "Examination", amount: 5000 },
    ...(i % 3 === 0 ? [{ label: "Transport", amount: 18000 }] : []),
  ];
  const total = items.reduce((a, b) => a + b.amount, 0);
  const paid = s.outstandingFees === 0 ? total : Math.max(0, total - s.outstandingFees);
  return {
    id: `inv_${5000 + i}`,
    studentId: s.id,
    studentName: `${s.firstName} ${s.lastName}`,
    className: `${s.className}${s.arm}`,
    term: "First Term 2025/2026",
    total,
    paid,
    items,
    status: paid === 0 ? "unpaid" : paid >= total ? "paid" : "part_paid",
  } satisfies Invoice;
});

export const payments: Payment[] = invoices.slice(0, 32).map((inv, i) => ({
  id: `pay_${9000 + i}`,
  invoiceId: inv.id,
  studentName: inv.studentName,
  amount: [25000, 45000, 60000, 15000][i % 4]!,
  method: (["cash", "bank_transfer", "card", "pos", "online", "ussd"] as const)[i % 6]!,
  status: (["verified", "verified", "verified", "pending", "failed", "verified"] as const)[i % 6]!,
  reference: `FN-${String(83000 + i)}`,
  recordedBy: i % 3 === 0 ? "Bursar Halima" : "Online gateway",
  createdAt: new Date(Date.now() - i * 7200_000).toISOString(),
}));

export const resultSheets: ResultSheet[] = [
  "JSS 1A",
  "JSS 2A",
  "JSS 2B",
  "Primary 5A",
  "SS 1A",
  "SS 1B",
].flatMap((className, ci) =>
  ["Mathematics", "English Language"].map((subject, si) => ({
    id: `res_${ci}${si}`,
    className,
    subject,
    term: "First Term 2025/2026",
    status: (["draft", "submitted", "under_review", "approved", "published"] as const)[
      (ci * 2 + si) % 5
    ]!,
    rows: students.slice(ci * 12, ci * 12 + 12).map((s) => ({
      studentId: s.id,
      studentName: `${s.firstName} ${s.lastName}`,
      ca1: Math.round(5 + rnd() * 10),
      ca2: Math.round(5 + rnd() * 10),
      assignment: Math.round(5 + rnd() * 5),
      exam: Math.round(25 + rnd() * 35),
    })),
  })),
);

export const timetable: TimetableSlot[] = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
].flatMap((day, di) =>
  ["08:00 – 08:45", "08:45 – 09:30", "10:00 – 10:45", "11:00 – 11:45"].map((period, pi) => ({
    id: `slot_${di}${pi}`,
    day,
    period,
    className: "JSS 2A",
    subject: SUBJECTS[(di + pi) % SUBJECTS.length]!,
    teacher: staff[(di * 4 + pi) % staff.length]!.fullName,
    room: `Room ${10 + ((di + pi) % 5)}`,
  })),
);

export const lessonPlans: LessonPlan[] = [
  {
    id: "lp_1",
    subject: "Mathematics",
    className: "JSS 2A",
    topic: "Simple equations in one variable",
    duration: "45 minutes",
    objectives:
      "By the end of the lesson students will solve simple linear equations and check their solutions.",
    previousKnowledge: "Students can add, subtract and multiply directed numbers.",
    introduction:
      "Begin with a market pricing problem: 3 oranges cost ₦150, what is the price of one?",
    teacherActivities:
      "Model balancing both sides of an equation on the board; guide two worked examples.",
    studentActivities: "Solve five equations in pairs; present one solution on the board.",
    materials: "Chalkboard, equation flashcards, exercise books.",
    assessment: "Five-question class exercise; mark and review immediately.",
    homework: "Exercise 4b, questions 1–10.",
    updatedAt: new Date(Date.now() - 86_400_000).toISOString(),
  },
];

export const announcements: Announcement[] = [
  {
    id: "ann_1",
    title: "First term examination begins 24 August",
    body: "All classes resume examination timetable on Monday. Parents should ensure fees are settled before the examination week.",
    audience: ["Parents", "Students", "Teachers"],
    createdAt: new Date(Date.now() - 3600_000).toISOString(),
    author: "Mrs. Aisha Bello",
  },
  {
    id: "ann_2",
    title: "PTA meeting — Saturday 10am",
    body: "The termly PTA meeting holds in the school hall. Class teachers will be available for one-on-one discussions.",
    audience: ["Parents"],
    createdAt: new Date(Date.now() - 86_400_000 * 2).toISOString(),
    author: "Mrs. Aisha Bello",
  },
];

export const notifications: AppNotification[] = [
  {
    id: "n1",
    type: "payment",
    title: "Payment verified",
    body: "₦45,000 school fees payment for Ahmed Abubakar was verified.",
    createdAt: new Date(Date.now() - 1800_000).toISOString(),
    read: false,
  },
  {
    id: "n2",
    type: "result",
    title: "23 result sheets await approval",
    body: "First Term results for JSS 1 – SS 3 are submitted and waiting for your approval.",
    createdAt: new Date(Date.now() - 7200_000).toISOString(),
    read: false,
  },
  {
    id: "n3",
    type: "subscription",
    title: "Renewal in 7 days",
    body: "Your 401–600 student plan renews on 1 September.",
    createdAt: new Date(Date.now() - 86_400_000).toISOString(),
    read: false,
  },
  {
    id: "n4",
    type: "attendance",
    title: "Attendance below threshold",
    body: "18 students have attendance below 70% this term.",
    createdAt: new Date(Date.now() - 172_800_000).toISOString(),
    read: true,
  },
  {
    id: "n5",
    type: "security",
    title: "New sign-in",
    body: "New sign-in from Chrome on Android in Kano.",
    createdAt: new Date(Date.now() - 259_200_000).toISOString(),
    read: true,
  },
];

export const platformSchools: PlatformSchool[] = Array.from({ length: 42 }, (_, i) => ({
  id: `sch_${100 + i}`,
  name: `${["Al-Noor", "Bright Future", "Cornerstone", "Greenfield", "Royal Crest", "Hilltop", "Zamani", "Divine Grace"][i % 8]} ${["Academy", "College", "International School", "Model School"][i % 4]}`,
  state: STATES[i % STATES.length]!,
  students: 60 + Math.floor(rnd() * 1800),
  tierId: ["t100", "t200", "t400", "t600", "t1000", "t1500"][i % 6]!,
  status: (
    ["active", "active", "active", "trial", "pending_payment", "suspended", "grace"] as const
  )[i % 7]!,
  mrr: [8000, 13000, 19000, 25000, 37000, 49000][i % 6]!,
  createdAt: new Date(Date.now() - i * 86_400_000 * 6).toISOString(),
}));

export const attendanceStatuses: AttendanceStatus[] = ["present", "absent", "late", "excused"];
