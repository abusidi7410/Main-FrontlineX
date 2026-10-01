import { beforeEach, describe, expect, it, vi } from "vitest";

import { createStudent, type StudentInput } from "@/services/students.service";
import { apiFetch } from "@/api/client";

/**
 * Registration now returns billing information alongside the student, because
 * the registrar has to tell the family what is owed and the student is not
 * usable until it is paid. The invoice fields must not leak into the Student
 * object, and a school with no fee structure yet must be handled rather than
 * throwing on undefined.
 */
vi.mock("@/api/client", () => ({ apiFetch: vi.fn() }));

const student = {
  id: "9",
  firstName: "Ada",
  lastName: "Nwosu",
  className: "JSS 1",
  status: "pending_payment",
};

const input: StudentInput = {
  firstName: "Ada",
  lastName: "Nwosu",
  gender: "female",
  className: "JSS 1",
  arm: "A",
  dateOfBirth: "2014-05-02",
  guardianName: "Mrs N",
  guardianPhone: "08012345678",
};

describe("createStudent", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("returns the one-time registration invoice raised at registration", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      ...student,
      invoiceId: "44",
      invoiceTotal: "5000.00",
      registrationFeeConfigured: true,
    });
    const result = await createStudent(input);
    expect(result.invoiceId).toBe("44");
    expect(result.invoiceTotal).toBe("5000.00");
    expect(result.registrationFeeConfigured).toBe(true);
    expect(result.student.status).toBe("pending_payment");
  });

  it("keeps the invoice fields out of the student object", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      ...student,
      invoiceId: "44",
      invoiceTotal: "5000.00",
      registrationFeeConfigured: true,
    });
    const result = await createStudent(input);
    expect(result.student).not.toHaveProperty("invoiceId");
    expect(result.student).not.toHaveProperty("registrationFeeConfigured");
  });

  it("reports an unconfigured fee structure instead of throwing", async () => {
    // No registration fee applies; regular school fees are billed separately.
    vi.mocked(apiFetch).mockResolvedValue({ ...student, registrationFeeConfigured: false });
    const result = await createStudent(input);
    expect(result.registrationFeeConfigured).toBe(false);
    expect(result.invoiceId).toBe("");
    expect(result.invoiceTotal).toBe("");
    expect(result.student.id).toBe("9");
  });

  it("tolerates a response with no billing fields at all", async () => {
    vi.mocked(apiFetch).mockResolvedValue(student);
    const result = await createStudent(input);
    expect(result.registrationFeeConfigured).toBe(false);
    expect(result.student.firstName).toBe("Ada");
  });

  it("posts the form to the versioned students endpoint", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...student, registrationFeeConfigured: true });
    await createStudent(input);
    expect(apiFetch).toHaveBeenCalledWith("/students", {
      method: "POST",
      body: input,
    });
  });
});
