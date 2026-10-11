import { describe, expect, it } from "vitest";
import { NAV_BY_ROLE, flattenNav } from "@/permissions/navigation";

const KNOWN_ROUTES = new Set([
  "/dashboard",
  "/students",
  "/students/new",
  "/students/import",
  "/staff",
  "/staff/new",
  "/accounts",
  "/academics",
  "/attendance",
  "/attendance-overview",
  "/results",
  "/timetable",
  "/lesson-plans",
  "/promotion",
  "/finance",
  "/finance/invoices",
  "/fees",
  "/communication",
  "/notifications",
  "/ai",
  "/reports",
  "/settings",
  "/subscription",
  "/audit-logs",
  "/ussd",
  "/sync",
  "/my-classes",
  "/children",
  "/platform",
  "/platform/schools",
  "/platform/plans",
  "/platform/subscriptions",
  "/platform/payments",
  "/platform/activity",
  "/platform/audit",
  "/platform/settings",
]);

describe("hierarchical navigation", () => {
  it("points every entry at a real route (no disconnected links)", () => {
    for (const [role, items] of Object.entries(NAV_BY_ROLE)) {
      for (const entry of flattenNav(items)) {
        expect(KNOWN_ROUTES.has(entry.to), `${role}: ${entry.label} → ${entry.to}`).toBe(true);
      }
    }
  });

  it("keeps attendance grouped: take-register + records under one module", () => {
    const admin = NAV_BY_ROLE.school_admin;
    const attendance = admin.find((i) => i.label === "Attendance");
    expect(attendance?.children?.map((c) => c.to)).toEqual(
      expect.arrayContaining(["/attendance", "/attendance-overview"]),
    );
  });

  it("gives the platform manager exactly the 8 SaaS control sections", () => {
    const platform = NAV_BY_ROLE.platform_manager.map((i) => i.to);
    expect(platform).toEqual([
      "/platform",
      "/platform/schools",
      "/platform/plans",
      "/platform/subscriptions",
      "/platform/payments",
      "/platform/activity",
      "/platform/audit",
      "/platform/settings",
    ]);
  });

  it("keeps platform navigation separate from school navigation", () => {
    const schoolTargets = new Set(flattenNav(NAV_BY_ROLE.school_admin).map((e) => e.to));
    for (const entry of flattenNav(NAV_BY_ROLE.platform_manager)) {
      expect(schoolTargets.has(entry.to)).toBe(false);
    }
  });

  it("shows ordinary school roles no platform routes", () => {
    for (const role of [
      "school_admin",
      "principal",
      "teacher",
      "accountant",
      "secretary",
      "parent",
      "student",
    ] as const) {
      for (const entry of flattenNav(NAV_BY_ROLE[role])) {
        expect(entry.to.startsWith("/platform")).toBe(false);
      }
    }
  });
});
