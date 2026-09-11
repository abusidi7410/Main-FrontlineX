import { describe, expect, it } from "vitest";
import { ROLE_PERMISSIONS, ROLE_LABELS, can, canAny } from "@/permissions";

describe("can", () => {
  it("returns true when permission is present", () => {
    expect(can(["students.read", "students.write"] as const, "students.read")).toBe(true);
  });

  it("returns false when permission is absent", () => {
    expect(can(["students.read"] as const, "students.write")).toBe(false);
  });

  it("returns false for undefined permissions", () => {
    expect(can(undefined, "students.read")).toBe(false);
  });
});

describe("canAny", () => {
  it("returns true if at least one required permission is present", () => {
    expect(canAny(["finance.read"] as const, ["finance.read", "finance.write"])).toBe(true);
  });

  it("returns false if none of the required permissions are present", () => {
    expect(canAny(["students.read"] as const, ["finance.read", "finance.write"])).toBe(false);
  });

  it("returns false for undefined permissions", () => {
    expect(canAny(undefined, ["finance.read"])).toBe(false);
  });
});

describe("ROLE_LABELS", () => {
  it("has labels for all roles", () => {
    const roles = Object.keys(ROLE_PERMISSIONS);
    for (const role of roles) {
      expect(ROLE_LABELS[role as keyof typeof ROLE_LABELS]).toBeDefined();
      expect(typeof ROLE_LABELS[role as keyof typeof ROLE_LABELS]).toBe("string");
    }
  });
});

describe("ROLE_PERMISSIONS", () => {
  it("school_admin has full access", () => {
    const adminPerms = ROLE_PERMISSIONS.school_admin;
    expect(adminPerms).toContain("students.read");
    expect(adminPerms).toContain("students.write");
    expect(adminPerms).toContain("students.import");
    expect(adminPerms).toContain("results.publish");
    expect(adminPerms).toContain("finance.write");
    expect(adminPerms).toContain("settings.write");
    expect(adminPerms).toContain("ai.academic");
    expect(adminPerms).toContain("ai.finance");
    expect(adminPerms).toContain("ai.teaching");
  });

  it("teacher lacks finance and settings write", () => {
    const teacherPerms = ROLE_PERMISSIONS.teacher;
    expect(teacherPerms).not.toContain("finance.read");
    expect(teacherPerms).not.toContain("finance.write");
    expect(teacherPerms).not.toContain("settings.write");
    expect(teacherPerms).not.toContain("results.publish");
    expect(teacherPerms).not.toContain("students.import");
    expect(teacherPerms).not.toContain("subscription.read");
  });

  it("accountant cannot access results or attendance", () => {
    const acct = ROLE_PERMISSIONS.accountant;
    expect(acct).not.toContain("results.write");
    expect(acct).not.toContain("results.publish");
    expect(acct).not.toContain("attendance.write");
    expect(acct).not.toContain("settings.write");
  });

  it("parent has only ai.parent", () => {
    expect(ROLE_PERMISSIONS.parent).toEqual(["ai.parent"]);
  });

  it("platform_manager has platform.manage", () => {
    expect(ROLE_PERMISSIONS.platform_manager).toContain("platform.manage");
    expect(ROLE_PERMISSIONS.platform_manager).toContain("audit.read");
  });
});
