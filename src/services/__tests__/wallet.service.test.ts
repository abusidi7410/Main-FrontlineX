import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/api/client";
import {
  activateStudent,
  getWallet,
  listStudentAccess,
  sendAlert,
  setSchoolMessaging,
  startDeposit,
  verifyDeposit,
} from "@/services/wallet.service";

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, apiFetch: vi.fn() };
});

/**
 * Wallet endpoints are versioned under /billing and always carry the /api/v1
 * prefix via the shared client — these tests pin the paths and methods so a
 * refactor cannot silently point money at the wrong route. They never retry a
 * failed write: replaying a debit the user did not ask for is a billing bug.
 */
describe("wallet service routes", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("reads the wallet overview", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ balanceKobo: 4000 });
    await expect(getWallet()).resolves.toEqual({ balanceKobo: 4000 });
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe("/billing/wallet");
  });

  it("starts a deposit with the amount in kobo", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ reference: "DEP-1" });
    await startDeposit(50000);
    const [path, options] = vi.mocked(apiFetch).mock.calls[0] as [
      string,
      { method: string; body: unknown },
    ];
    expect(path).toBe("/billing/deposits");
    expect(options.method).toBe("POST");
    expect(options.body).toEqual({ amountKobo: 50000 });
  });

  it("verifies a deposit exactly once per call", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ status: "success" });
    await expect(verifyDeposit("DEP-1")).resolves.toEqual({ status: "success" });
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe("/billing/deposits/verify/DEP-1");
    expect(vi.mocked(apiFetch)).toHaveBeenCalledTimes(1);
  });

  it("activates a student with a single POST", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ created: true });
    await activateStudent("stu-1");
    const [path, options] = vi.mocked(apiFetch).mock.calls[0] as [string, { method: string }];
    expect(path).toBe("/billing/students/stu-1/activate");
    expect(options.method).toBe("POST");
    expect(vi.mocked(apiFetch)).toHaveBeenCalledTimes(1);
  });

  it("lists student access with search and pagination", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ results: [], count: 0 });
    await listStudentAccess("ada");
    const [path, options] = vi.mocked(apiFetch).mock.calls[0] as [string, { query: unknown }];
    expect(path).toBe("/billing/students");
    expect(options.query).toEqual({ search: "ada", page: 1, pageSize: 20 });
  });

  it("sends an alert with a single POST carrying the idempotency reference", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ reference: "SMS-1" });
    await sendAlert({ recipient: "+2348000000001", message: "Hi", reference: "SMS-1" });
    const [path, options] = vi.mocked(apiFetch).mock.calls[0] as [
      string,
      { method: string; body: unknown },
    ];
    expect(path).toBe("/billing/alerts");
    expect(options.method).toBe("POST");
    expect(options.body).toEqual({
      recipient: "+2348000000001",
      message: "Hi",
      reference: "SMS-1",
    });
    expect(vi.mocked(apiFetch)).toHaveBeenCalledTimes(1);
  });

  it("toggles the school messaging switch with PATCH", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ schoolEnabled: false });
    await setSchoolMessaging(false);
    const [path, options] = vi.mocked(apiFetch).mock.calls[0] as [
      string,
      { method: string; body: unknown },
    ];
    expect(path).toBe("/billing/messaging");
    expect(options.method).toBe("PATCH");
    expect(options.body).toEqual({ schoolEnabled: false });
  });
});
