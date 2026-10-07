import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "@/api/client";
import { getChildAttendance, getChildPromotion, listChildren } from "@/services/children.service";

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, apiFetch: vi.fn() };
});

describe("listChildren", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("hits the versioned parent portal endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      results: [],
      count: 0,
      page: 1,
      pageSize: 25,
      totalPages: 1,
    });
    await listChildren();
    expect(apiFetch).toHaveBeenCalledWith("/parents/me/children", { query: {} });
  });

  it("passes the page size through so the parent portal can page the family", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      results: [],
      count: 0,
      page: 1,
      pageSize: 100,
      totalPages: 1,
    });
    await listChildren({ pageSize: 100 });
    expect(apiFetch).toHaveBeenCalledWith("/parents/me/children", { query: { pageSize: 100 } });
  });
});

describe("getChildAttendance", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("reads one child's register", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      studentId: "7",
      summary: { recorded: 3, present: 2, late: 0, absent: 1, excused: 0, attendanceRate: 66.7 },
      records: [{ date: "2026-09-21", status: "present", className: "JSS 1" }],
    });
    const result = await getChildAttendance("7");
    expect(result.summary.present).toBe(2);
    expect(apiFetch).toHaveBeenCalledWith("/parents/me/children/7/attendance", { query: {} });
  });

  it("forwards an optional date range", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ summary: {}, records: [] });
    await getChildAttendance("7", { dateFrom: "2026-09-01", dateTo: "2026-09-30" });
    expect(apiFetch).toHaveBeenCalledWith("/parents/me/children/7/attendance", {
      query: { dateFrom: "2026-09-01", dateTo: "2026-09-30" },
    });
  });
});

describe("getChildPromotion", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("reads the suggestion for one child", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      enrolled: true,
      suggested: "promote",
      reason: "Meets the average and attendance thresholds with no failed subjects.",
      average: 78.5,
      nextClass: "JSS 2",
    });
    const result = await getChildPromotion("7");
    expect(result.suggested).toBe("promote");
    expect(apiFetch).toHaveBeenCalledWith("/parents/me/children/7/promotion");
  });
});
