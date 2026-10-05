import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, apiFetch } from "@/api/client";
import { getSchoolProfile, updateSchoolProfile } from "@/services/school.service";

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, apiFetch: vi.fn() };
});

const profile = {
  id: "sch_1",
  name: "Riverside Primary School",
  slug: "riverside",
  logoUrl: null,
  status: "active" as const,
  address: "12 Ada Street",
  state: "Rivers State",
  lga: "Port Harcourt",
  phone: "+234 800 000 0000",
  email: "fees@riverside.test",
  branding: {},
  studentCount: 120,
  staffCount: 9,
};

/**
 * The profile endpoint has a compatibility path for a backend deployment that
 * exposes the route under /schools/schools/profile/. That fallback must only
 * fire for a genuinely missing route: replaying a PATCH after a permission or
 * validation failure would send a second write the user never asked for.
 */
describe("school profile route compatibility", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("reads /schools/profile when it exists", async () => {
    vi.mocked(apiFetch).mockResolvedValue(profile);
    await expect(getSchoolProfile()).resolves.toEqual(profile);
    expect(vi.mocked(apiFetch)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe("/schools/profile");
  });

  it("falls back to /schools/schools/profile on a 404", async () => {
    vi.mocked(apiFetch)
      .mockRejectedValueOnce(new ApiRequestError("Not found.", 404))
      .mockResolvedValueOnce(profile);
    await expect(getSchoolProfile()).resolves.toEqual(profile);
    expect(vi.mocked(apiFetch).mock.calls[1]?.[0]).toBe("/schools/schools/profile");
  });

  it("surfaces a permission failure instead of retrying the write", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new ApiRequestError("Forbidden.", 403));
    await expect(updateSchoolProfile({ name: "New Name" })).rejects.toThrow("Forbidden.");
    expect(vi.mocked(apiFetch)).toHaveBeenCalledTimes(1);
    const [path, options] = vi.mocked(apiFetch).mock.calls[0] as [string, { method: string }];
    expect(path).toBe("/schools/profile");
    expect(options.method).toBe("PATCH");
  });

  it("does not retry a validation failure", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new ApiRequestError("Invalid payload.", 400));
    await expect(updateSchoolProfile({ name: "" })).rejects.toThrow("Invalid payload.");
    expect(vi.mocked(apiFetch)).toHaveBeenCalledTimes(1);
  });

  it("does not retry a network failure", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(updateSchoolProfile({ name: "Riverside" })).rejects.toThrow("Failed to fetch");
    expect(vi.mocked(apiFetch)).toHaveBeenCalledTimes(1);
  });
});
