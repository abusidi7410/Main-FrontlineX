import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, ApiRequestError } from "@/api/client";
import { getReportCard } from "@/services/reports.service";

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, apiFetch: vi.fn() };
});

describe("getReportCard", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("returns the card when one exists", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ student: { id: "7" }, subjects: [] });
    const card = await getReportCard("7");
    expect(card).toEqual({ student: { id: "7" }, subjects: [] });
  });

  it("returns null for a 404 so the screens can say nothing is published yet", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new ApiRequestError("Not found", 404));
    const value = await getReportCard("7");
    expect(value).toBeNull();
  });

  it("re-raises anything that is not a 404", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new ApiRequestError("Boom", 500));
    await expect(getReportCard("7")).rejects.toMatchObject({ status: 500 });
  });
});
