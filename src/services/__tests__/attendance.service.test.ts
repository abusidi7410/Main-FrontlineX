import { describe, expect, it, vi } from "vitest";
import {
  assignedClassNames,
  visibleClassNames,
  type ClassTeacherAssignment,
} from "@/services/attendance.service";

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, apiFetch: vi.fn() };
});

function assignment(className: string, staffId: string): ClassTeacherAssignment {
  return { className, classId: 1, staffId, staffName: "Teacher", session: "2025/2026" };
}

describe("assignedClassNames", () => {
  it("returns only the classes designated to the given staff member", () => {
    const rows = [assignment("JSS 1", "9"), assignment("JSS 2", "10"), assignment("JSS 3", "9")];
    expect(assignedClassNames(rows, "9")).toEqual(["JSS 1", "JSS 3"]);
  });

  it("dedupes a class assigned twice and keeps assignment order", () => {
    const rows = [assignment("JSS 1", "9"), assignment("JSS 1", "9")];
    expect(assignedClassNames(rows, "9")).toEqual(["JSS 1"]);
  });

  it("returns an empty list without a linked staff record or designation", () => {
    const rows = [assignment("JSS 1", "9")];
    expect(assignedClassNames(rows, null)).toEqual([]);
    expect(assignedClassNames(rows, undefined)).toEqual([]);
    expect(assignedClassNames(rows, "10")).toEqual([]);
    expect(assignedClassNames([], "9")).toEqual([]);
  });
});

describe("visibleClassNames", () => {
  it("shows only the assigned classes for a scoped teacher", () => {
    expect(visibleClassNames(["JSS 1", "JSS 2", "JSS 3"], ["JSS 2"], true)).toEqual(["JSS 2"]);
  });

  it("shows the timetable classes for everyone else, sorted and deduped", () => {
    expect(visibleClassNames(["JSS 2", "JSS 1", "JSS 1"], ["JSS 3"], false)).toEqual([
      "JSS 1",
      "JSS 2",
    ]);
  });

  it("shows an empty list for a scoped teacher with no designation", () => {
    expect(visibleClassNames(["JSS 1"], [], true)).toEqual([]);
  });
});
