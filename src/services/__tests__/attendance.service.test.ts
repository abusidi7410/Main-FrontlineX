import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "@/api/client";
import {
  assignClassTeacher,
  assignedClassNames,
  checkInToClass,
  decideTeacherCheckIn,
  getMyClassAttendance,
  getTeacherCheckIns,
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

describe("assignClassTeacher", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("posts an unassign payload to clear a designation", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ className: "JSS 1", classTeacher: "" });
    await assignClassTeacher({ className: "JSS 1", assign: false });
    expect(apiFetch).toHaveBeenCalledWith("/attendance/class-teachers", {
      method: "POST",
      body: { className: "JSS 1", assign: false },
    });
  });

  it("posts the staff designation to assign a class", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ className: "JSS 1", classTeacher: "Mrs Ade" });
    await assignClassTeacher({ className: "JSS 1", staffId: "9" });
    expect(apiFetch).toHaveBeenCalledWith("/attendance/class-teachers", {
      method: "POST",
      body: { className: "JSS 1", staffId: "9" },
    });
  });
});

describe("teacher class check-ins", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("loads the caller's own day from the school clock", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      date: "2026-10-15",
      sessions: [],
      summary: { total: 0 },
    });
    await getMyClassAttendance();
    expect(apiFetch).toHaveBeenCalledWith("/attendance/teacher-checkins/my-day");
  });

  it("posts only coordinates — never a claimed status", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ id: 1, status: "present_verified" });
    await checkInToClass({ entryId: 42, latitude: 6.5, longitude: 3.3, accuracy: 12 });
    expect(apiFetch).toHaveBeenCalledWith("/attendance/teacher-checkins/check-in", {
      method: "POST",
      body: { entryId: 42, latitude: 6.5, longitude: 3.3, accuracy: 12 },
    });
  });

  it("sends every monitor filter as a query string value", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      records: [],
      count: 0,
      page: 2,
      pageSize: 25,
      totalPages: 0,
      summary: { total: 0, counts: {} },
    });
    await getTeacherCheckIns({
      date: "2026-10-15",
      staffId: "9",
      className: "JSS 1",
      subject: "Mathematics",
      status: ["missed"],
      search: "Ade",
      page: 2,
      pageSize: 25,
    });
    expect(apiFetch).toHaveBeenCalledWith("/attendance/teacher-checkins", {
      query: {
        date: "2026-10-15",
        staffId: "9",
        className: "JSS 1",
        subject: "Mathematics",
        status: "missed",
        search: "Ade",
        page: 2,
        pageSize: 25,
      },
    });
  });

  it("omits empty filters so an untouched board means no query params", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      records: [],
      count: 0,
      page: 1,
      pageSize: 25,
      totalPages: 0,
      summary: { total: 0, counts: {} },
    });
    await getTeacherCheckIns({ date: "2026-10-15", status: [] });
    expect(apiFetch).toHaveBeenCalledWith("/attendance/teacher-checkins", {
      query: { date: "2026-10-15" },
    });
  });

  it("posts a cancel decision with its reason to the session's decision endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ id: 7, status: "cancelled" });
    await decideTeacherCheckIn({ id: 7, action: "cancel", note: "School trip" });
    expect(apiFetch).toHaveBeenCalledWith("/attendance/teacher-checkins/7/decision", {
      method: "POST",
      body: { action: "cancel", note: "School trip" },
    });
  });

  it("posts an override with a forced status and a required reason", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ id: 7, status: "late_verified" });
    await decideTeacherCheckIn({
      id: 7,
      action: "override",
      status: "late_verified",
      note: "Traffic confirmed",
    });
    expect(apiFetch).toHaveBeenCalledWith("/attendance/teacher-checkins/7/decision", {
      method: "POST",
      body: { action: "override", status: "late_verified", note: "Traffic confirmed" },
    });
  });

  it("never sends a status field for a cancel decision", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ id: 7, status: "cancelled" });
    await decideTeacherCheckIn({ id: 7, action: "cancel" });
    const body = vi.mocked(apiFetch).mock.calls[0]?.[1]?.body as Record<string, unknown>;
    expect(body).not.toHaveProperty("status");
  });
});
