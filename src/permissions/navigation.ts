import type { Role } from "@/types";

/**
 * Hierarchical navigation: Main module → Sub-modules → existing routes.
 *
 * Every `to` below is a pre-existing route — this file only groups them, it
 * never invents screens. A main module with `children` renders as one
 * expandable sidebar section whose header only expands/collapses; the
 * children are the actual destinations, each labelled distinctly from the
 * parent (no "Students → Student List" echo). The parent's own `to` always
 * matches one of its children and is used only as the fallback target for
 * the collapsed icon rail and the mobile bottom bar. A main module without
 * children is a direct link.
 * `mobile` marks the entries that fit the 5-slot bottom bar on phones.
 */
export interface NavChild {
  label: string;
  to: string;
}

export interface NavItem {
  label: string;
  to: string;
  icon: string;
  group?: string;
  mobile?: boolean;
  children?: NavChild[];
}

const SCHOOL_ADMIN: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  // People, admissions and staff logins are one module: the same pupils and
  // staff, reached from one place instead of four sidebar entries.
  {
    label: "People",
    to: "/students",
    icon: "users",
    group: "People",
    mobile: true,
    children: [
      { label: "All Students", to: "/students" },
      { label: "Staff & Accounts", to: "/staff" },
      { label: "Applications", to: "/admissions" },
      { label: "New Application", to: "/admissions/new" },
      { label: "Admission Requirements", to: "/admissions/settings" },
    ],
  },
  // Attendance sits with academics: both describe what happens in a lesson.
  {
    label: "Academics",
    to: "/academics",
    icon: "graduation",
    group: "Academics",
    mobile: true,
    children: [
      { label: "Subjects & Classes", to: "/academics" },
      { label: "Timetable", to: "/timetable" },
      { label: "Lesson Plans", to: "/lesson-plans" },
      { label: "Promotion Centre", to: "/promotion" },
      { label: "Results", to: "/results" },
      { label: "Take Register", to: "/attendance" },
      { label: "Attendance Records", to: "/attendance-overview" },
      { label: "Teacher Check-ins", to: "/teacher-attendance" },
    ],
  },
  {
    label: "Finance",
    to: "/finance",
    icon: "wallet",
    group: "Finance",
    mobile: true,
    children: [
      { label: "Overview", to: "/finance" },
      { label: "Invoices", to: "/finance/invoices" },
      { label: "Receipts", to: "/finance/receipts" },
      { label: "Wallet & Billing", to: "/wallet" },
    ],
  },
  // Announcements, notifications, reports and the assistant are all
  // outward-facing communication, so they share one module.
  {
    label: "Engagement",
    to: "/communication",
    icon: "megaphone",
    group: "Engagement",
    mobile: true,
    children: [
      { label: "Announcements", to: "/communication" },
      { label: "Notifications", to: "/notifications" },
      { label: "Reports", to: "/reports" },
      { label: "AI Assistant", to: "/ai" },
    ],
  },
  {
    label: "Manage",
    to: "/settings",
    icon: "settings",
    group: "Manage",
    children: [
      { label: "School Settings", to: "/settings" },
      { label: "Audit Logs", to: "/audit-logs" },
      { label: "USSD", to: "/ussd" },
    ],
  },
];

const PRINCIPAL: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  {
    label: "Students",
    to: "/students",
    icon: "users",
    group: "People",
    mobile: true,
    children: [
      { label: "All Students", to: "/students" },
      { label: "Login Accounts", to: "/accounts" },
    ],
  },
  {
    label: "Admissions",
    to: "/admissions",
    icon: "userCog",
    group: "People",
    children: [
      { label: "Applications", to: "/admissions" },
      { label: "New Application", to: "/admissions/new" },
    ],
  },
  {
    label: "Academics",
    to: "/attendance",
    icon: "clipboard",
    group: "Academics",
    mobile: true,
    children: [
      { label: "Take Register", to: "/attendance" },
      // A principal is read-only on attendance, so the overview (who has
      // taken their register) is the more useful screen for them.
      { label: "Records & History", to: "/attendance-overview" },
      { label: "Teacher Check-ins", to: "/teacher-attendance" },
      { label: "Results", to: "/results" },
      { label: "Timetable", to: "/timetable" },
      { label: "Promotion Centre", to: "/promotion" },
    ],
  },
  {
    label: "Finance",
    to: "/finance/invoices",
    icon: "wallet",
    group: "Finance",
    mobile: true,
    children: [
      { label: "Invoices", to: "/finance/invoices" },
      { label: "Receipts", to: "/finance/receipts" },
    ],
  },
  {
    label: "Communication",
    to: "/communication",
    icon: "megaphone",
    group: "Engagement",
    children: [
      { label: "Announcements", to: "/communication" },
      { label: "Notifications", to: "/notifications" },
    ],
  },
  {
    label: "Manage",
    to: "/reports",
    icon: "chart",
    group: "Manage",
    mobile: true,
    children: [
      { label: "Reports", to: "/reports" },
      { label: "AI Assistant", to: "/ai" },
      // Settings is where the Payment Structure lives, so a principal needs
      // it in order to see prices. It renders read-only without
      // `finance.structure`.
      { label: "School Settings", to: "/settings" },
    ],
  },
];

const TEACHER: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Today", mobile: true },
  { label: "My Classes", to: "/my-classes", icon: "users", group: "Today", mobile: true },
  {
    label: "Teaching",
    to: "/attendance",
    icon: "clipboard",
    group: "Teaching",
    mobile: true,
    children: [
      { label: "Take Register", to: "/attendance" },
      // Scoped to the teacher's own classes by the API, so this is their own
      // "did everyone take the register" board rather than the school's.
      { label: "Records & History", to: "/attendance-overview" },
      { label: "Results", to: "/results" },
      { label: "Lesson Plans", to: "/lesson-plans" },
      { label: "Timetable", to: "/timetable" },
    ],
  },
  {
    label: "Engagement",
    to: "/notifications",
    icon: "bell",
    group: "Teaching",
    mobile: true,
    children: [
      { label: "Notifications", to: "/notifications" },
      { label: "AI Assistant", to: "/ai" },
    ],
  },
  { label: "Sync Centre", to: "/sync", icon: "refresh", group: "Device", mobile: true },
];

const ACCOUNTANT: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  {
    label: "Finance",
    to: "/finance",
    icon: "wallet",
    group: "Finance",
    mobile: true,
    children: [
      { label: "Payment Overview", to: "/finance" },
      { label: "Invoices", to: "/finance/invoices" },
      { label: "Receipts", to: "/finance/receipts" },
      { label: "Students", to: "/students" },
      { label: "Reports", to: "/reports" },
    ],
  },
  {
    label: "Support",
    to: "/notifications",
    icon: "bell",
    group: "Support",
    mobile: true,
    children: [
      { label: "Admission Applications", to: "/admissions" },
      { label: "Notifications", to: "/notifications" },
      { label: "AI Assistant", to: "/ai" },
      { label: "School Settings", to: "/settings" },
    ],
  },
];

const SECRETARY: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  {
    label: "People",
    to: "/students",
    icon: "users",
    group: "People",
    mobile: true,
    children: [
      { label: "All Students", to: "/students" },
      { label: "Login Accounts", to: "/accounts" },
      { label: "Take Register", to: "/attendance" },
    ],
  },
  {
    label: "Admissions",
    to: "/admissions",
    icon: "userCog",
    group: "People",
    children: [
      { label: "Applications", to: "/admissions" },
      { label: "New Application", to: "/admissions/new" },
    ],
  },
  {
    label: "Finance",
    to: "/finance/receipts",
    icon: "receipt",
    group: "Finance",
    children: [{ label: "Receipts", to: "/finance/receipts" }],
  },
  {
    label: "Communication",
    to: "/communication",
    icon: "megaphone",
    group: "Engagement",
    mobile: true,
    children: [
      { label: "Announcements", to: "/communication" },
      { label: "Notifications", to: "/notifications" },
    ],
  },
];

const PARENT: NavItem[] = [
  {
    label: "Family",
    to: "/dashboard",
    icon: "home",
    group: "Family",
    mobile: true,
    children: [
      { label: "Home", to: "/dashboard" },
      { label: "My Children", to: "/children" },
      { label: "Fees", to: "/fees" },
    ],
  },
  {
    label: "School",
    to: "/communication",
    icon: "megaphone",
    group: "School",
    mobile: true,
    children: [
      { label: "Announcements", to: "/communication" },
      { label: "Notifications", to: "/notifications" },
      { label: "AI Assistant", to: "/ai" },
    ],
  },
];

const STUDENT: NavItem[] = [
  {
    label: "Learning",
    to: "/dashboard",
    icon: "home",
    group: "Learning",
    mobile: true,
    children: [
      { label: "Home", to: "/dashboard" },
      { label: "Timetable", to: "/timetable" },
      { label: "Results", to: "/results" },
    ],
  },
  {
    label: "School",
    to: "/communication",
    icon: "megaphone",
    group: "School",
    mobile: true,
    children: [
      { label: "Announcements", to: "/communication" },
      { label: "Notifications", to: "/notifications" },
      { label: "AI Assistant", to: "/ai" },
    ],
  },
];

/**
 * Platform Manager — kept entirely separate from school navigation.
 * Eight sections per the SaaS control spec; related actions live inside the
 * section's page (dialogs/tabs) rather than as extra sidebar entries.
 */
const PLATFORM: NavItem[] = [
  { label: "Overview", to: "/platform", icon: "home", group: "Platform", mobile: true },
  { label: "Schools", to: "/platform/schools", icon: "building", group: "Platform", mobile: true },
  { label: "Payments & Revenue", to: "/platform/payments", icon: "wallet", group: "Revenue" },
  { label: "Activity", to: "/platform/activity", icon: "audit", group: "Operations" },
  { label: "Analytics", to: "/platform/analytics", icon: "chart", group: "Operations" },
  { label: "Support", to: "/platform/support", icon: "lifebuoy", group: "Operations" },
  {
    label: "Audit Logs",
    to: "/platform/audit",
    icon: "shield",
    group: "Operations",
    mobile: true,
  },
  { label: "Settings", to: "/platform/settings", icon: "settings", group: "Operations" },
];

export const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  platform_manager: PLATFORM,
  school_admin: SCHOOL_ADMIN,
  principal: PRINCIPAL,
  teacher: TEACHER,
  accountant: ACCOUNTANT,
  secretary: SECRETARY,
  parent: PARENT,
  student: STUDENT,
};

export const HOME_BY_ROLE: Record<Role, string> = {
  platform_manager: "/platform",
  school_admin: "/dashboard",
  principal: "/dashboard",
  teacher: "/dashboard",
  accountant: "/dashboard",
  secretary: "/dashboard",
  parent: "/dashboard",
  student: "/dashboard",
};

/** Flatten main modules + sub-modules into link targets (for tests/search). */
export function flattenNav(items: NavItem[]): { label: string; to: string }[] {
  const out: { label: string; to: string }[] = [];
  for (const item of items) {
    out.push({ label: item.label, to: item.to });
    for (const child of item.children ?? []) out.push({ label: child.label, to: child.to });
  }
  return out;
}
