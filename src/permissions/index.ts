import type { Permission, Role } from "@/types";

export const ROLE_LABELS: Record<Role, string> = {
  platform_manager: "Platform Manager",
  school_admin: "School Administrator",
  principal: "Principal",
  teacher: "Teacher",
  accountant: "Bursar / Accountant",
  secretary: "School Secretary",
  parent: "Parent / Guardian",
  student: "Student",
};

/**
 * Mirror of the backend role→permission matrix. This drives navigation and
 * permission-aware UI only — the API remains the authority on every request.
 */
export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  platform_manager: [
    "platform.manage",
    "subscription.read",
    "subscription.write",
    "audit.read",
    "reports.read",
    "ai.platform",
    "settings.read",
    "settings.write",
  ],
  school_admin: [
    "students.read",
    "students.write",
    "students.import",
    "staff.read",
    "staff.write",
    "accounts.read",
    "accounts.write",
    "academics.read",
    "academics.write",
    "attendance.read",
    "attendance.write",
    "results.read",
    "results.write",
    "results.approve",
    "results.publish",
    "finance.read",
    "finance.write",
    "finance.verify",
    "timetable.read",
    "timetable.write",
    "lessonplans.read",
    "lessonplans.write",
    "communication.read",
    "communication.write",
    "reports.read",
    "subscription.read",
    "subscription.write",
    "settings.read",
    "settings.write",
    "audit.read",
    "ai.academic",
    "ai.finance",
    "ai.teaching",
  ],
  principal: [
    "students.read",
    "students.write",
    "staff.read",
    "staff.write",
    "accounts.read",
    "accounts.write",
    "academics.read",
    "academics.write",
    "attendance.read",
    "results.read",
    "results.approve",
    "timetable.read",
    "lessonplans.read",
    "communication.read",
    "communication.write",
    "reports.read",
    "settings.read",
    "ai.academic",
  ],
  teacher: [
    "students.read",
    "attendance.read",
    "attendance.write",
    "results.read",
    "results.write",
    "timetable.read",
    "lessonplans.read",
    "lessonplans.write",
    "communication.read",
    "ai.teaching",
  ],
  accountant: [
    "students.read",
    "finance.read",
    "finance.write",
    "finance.verify",
    "reports.read",
    "ai.finance",
  ],
  secretary: [
    "students.read",
    "students.write",
    "attendance.read",
    "communication.read",
    "communication.write",
    "accounts.read",
    "accounts.write",
  ],
  parent: ["ai.parent"],
  student: ["ai.student"],
};

export function can(permissions: Permission[] | undefined, permission: Permission) {
  return !!permissions?.includes(permission);
}

export function canAny(permissions: Permission[] | undefined, required: Permission[]) {
  return required.some((p) => can(permissions, p));
}
