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
  "/wallet",
  "/fees",
  "/communication",
  "/notifications",
  "/ai",
  "/reports",
  "/settings",
  "/audit-logs",
  "/ussd",
  "/sync",
  "/my-classes",
  "/children",
  "/platform",
  "/platform/schools",
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

  it("never repeats a module name as its own sub-module label", () => {
    for (const [role, items] of Object.entries(NAV_BY_ROLE)) {
      for (const item of items) {
        for (const child of item.children ?? []) {
          expect(
            child.label.toLowerCase() !== item.label.toLowerCase(),
            `${role}: "${item.label}" echoes as its own child`,
          ).toBe(true);
        }
      }
    }
  });

  it("reaches every parent target through one of its children (headers toggle, not link)", () => {
    for (const [role, items] of Object.entries(NAV_BY_ROLE)) {
      for (const item of items) {
        if (!item.children?.length) continue;
        expect(
          item.children.some((c) => c.to === item.to),
          `${role}: "${item.label}" header target ${item.to} has no child entry`,
        ).toBe(true);
      }
    }
  });

  it("gives the platform manager the SaaS control sections (no retired plans)", () => {
    const platform = NAV_BY_ROLE.platform_manager.map((i) => i.to);
    expect(platform).toEqual([
      "/platform",
      "/platform/schools",
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
