import type { Role } from "@/types";

export interface NavItem {
  label: string;
  to: string;
  icon: string;
  group?: string;
  mobile?: boolean;
}

const SCHOOL_ADMIN: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  { label: "Students", to: "/students", icon: "users", group: "People", mobile: true },
  { label: "Staff", to: "/staff", icon: "userCog", group: "People" },
  { label: "Academics", to: "/academics", icon: "graduation", group: "Academics" },
  { label: "Attendance", to: "/attendance", icon: "clipboard", group: "Academics", mobile: true },
  { label: "Results", to: "/results", icon: "award", group: "Academics" },
  { label: "Timetable", to: "/timetable", icon: "calendar", group: "Academics" },
  { label: "Lesson Plans", to: "/lesson-plans", icon: "notebook", group: "Academics" },
  { label: "Promotion Centre", to: "/promotion", icon: "promotion", group: "Academics" },
  { label: "Finance", to: "/finance", icon: "wallet", group: "Finance", mobile: true },
  { label: "Announcements", to: "/communication", icon: "megaphone", group: "Engagement" },
  { label: "AI Assistant", to: "/ai", icon: "sparkles", group: "Engagement" },
  { label: "Reports", to: "/reports", icon: "chart", group: "Manage" },
  { label: "Subscription", to: "/subscription", icon: "creditCard", group: "Manage" },
  { label: "Settings", to: "/settings", icon: "settings", group: "Manage" },
  { label: "USSD", to: "/ussd", icon: "ussd", group: "Manage" },
  { label: "Audit Logs", to: "/audit-logs", icon: "audit", group: "Manage" },
];

const PRINCIPAL: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  { label: "Students", to: "/students", icon: "users", group: "People", mobile: true },
  { label: "Staff", to: "/staff", icon: "userCog", group: "People" },
  { label: "Attendance", to: "/attendance", icon: "clipboard", group: "Academics", mobile: true },
  { label: "Results", to: "/results", icon: "award", group: "Academics", mobile: true },
  { label: "Timetable", to: "/timetable", icon: "calendar", group: "Academics" },
  { label: "Promotion Centre", to: "/promotion", icon: "promotion", group: "Academics" },
  { label: "Announcements", to: "/communication", icon: "megaphone", group: "Engagement" },
  { label: "AI Assistant", to: "/ai", icon: "sparkles", group: "Engagement" },
  { label: "Reports", to: "/reports", icon: "chart", group: "Manage" },
];

const TEACHER: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Today", mobile: true },
  { label: "My Classes", to: "/my-classes", icon: "users", group: "Today", mobile: true },
  { label: "Attendance", to: "/attendance", icon: "clipboard", group: "Teaching", mobile: true },
  { label: "Results", to: "/results", icon: "award", group: "Teaching", mobile: true },
  { label: "Lesson Plans", to: "/lesson-plans", icon: "notebook", group: "Teaching" },
  { label: "Timetable", to: "/timetable", icon: "calendar", group: "Teaching" },
  { label: "Sync Centre", to: "/sync", icon: "refresh", group: "Device" },
  { label: "AI Assistant", to: "/ai", icon: "sparkles", group: "Device", mobile: true },
];

const ACCOUNTANT: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  { label: "Students", to: "/students", icon: "users", group: "Finance" },
  { label: "Invoices", to: "/finance/invoices", icon: "receipt", group: "Finance", mobile: true },
  { label: "Payments", to: "/finance", icon: "wallet", group: "Finance", mobile: true },
  { label: "Reports", to: "/reports", icon: "chart", group: "Finance" },
  { label: "AI Assistant", to: "/ai", icon: "sparkles", group: "Support", mobile: true },
];

const SECRETARY: NavItem[] = [
  { label: "Dashboard", to: "/dashboard", icon: "home", group: "Overview", mobile: true },
  { label: "Students", to: "/students", icon: "users", group: "People", mobile: true },
  { label: "Attendance", to: "/attendance", icon: "clipboard", group: "People", mobile: true },
  {
    label: "Announcements",
    to: "/communication",
    icon: "megaphone",
    group: "Engagement",
    mobile: true,
  },
];

const PARENT: NavItem[] = [
  { label: "Home", to: "/dashboard", icon: "home", group: "Family", mobile: true },
  { label: "My Children", to: "/children", icon: "users", group: "Family", mobile: true },
  { label: "Fees", to: "/fees", icon: "wallet", group: "Family", mobile: true },
  { label: "Announcements", to: "/communication", icon: "megaphone", group: "School" },
  { label: "AI Assistant", to: "/ai", icon: "sparkles", group: "School", mobile: true },
];

const STUDENT: NavItem[] = [
  { label: "Home", to: "/dashboard", icon: "home", group: "Learning", mobile: true },
  { label: "Timetable", to: "/timetable", icon: "calendar", group: "Learning", mobile: true },
  { label: "Results", to: "/results", icon: "award", group: "Learning", mobile: true },
  { label: "Announcements", to: "/communication", icon: "megaphone", group: "School" },
  { label: "AI Assistant", to: "/ai", icon: "sparkles", group: "School", mobile: true },
];

const PLATFORM: NavItem[] = [
  { label: "Dashboard", to: "/platform", icon: "home", group: "Platform", mobile: true },
  { label: "Schools", to: "/platform/schools", icon: "building", group: "Platform", mobile: true },
  {
    label: "Subscriptions",
    to: "/platform/subscriptions",
    icon: "creditCard",
    group: "Revenue",
    mobile: true,
  },
  { label: "Analytics", to: "/platform/analytics", icon: "chart", group: "Revenue" },
  {
    label: "Security & Audit",
    to: "/platform/security",
    icon: "shield",
    group: "Operations",
    mobile: true,
  },
  { label: "Support", to: "/platform/support", icon: "lifebuoy", group: "Operations" },
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
