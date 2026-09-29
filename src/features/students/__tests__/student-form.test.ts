import { describe, expect, it } from "vitest";

import { studentSchema } from "@/features/students/student-form";

/**
 * The admission number is optional on create: omitting it is what makes the
 * server generate one. A required field here would block every user who
 * leaves the box empty, which is the intended default.
 */
const valid = {
  firstName: "Ada",
  lastName: "Nwosu",
  gender: "male" as const,
  dateOfBirth: "2014-05-02",
  className: "JSS 1",
  arm: "A",
  guardianName: "Mrs N",
  guardianPhone: "08012345678",
};

describe("studentSchema admission number", () => {
  it("accepts a blank admission number and drops it from the output", () => {
    const result = studentSchema.safeParse({ ...valid, admissionNumber: "" });
    expect(result.success).toBe(true);
    // The key must be absent, not an empty string, so the server sees "omit me".
    expect(result.success && result.data.admissionNumber).toBeUndefined();
  });

  it("accepts a missing admission number entirely", () => {
    const result = studentSchema.safeParse(valid);
    expect(result.success).toBe(true);
    expect(result.success && result.data.admissionNumber).toBeUndefined();
  });

  it("keeps a supplied number so legacy schools keep their own numbering", () => {
    const result = studentSchema.safeParse({ ...valid, admissionNumber: "  ALN/2019/07  " });
    expect(result.success).toBe(true);
    expect(result.success && result.data.admissionNumber).toBe("ALN/2019/07");
  });

  it("rejects a number longer than the backend column", () => {
    const result = studentSchema.safeParse({ ...valid, admissionNumber: "A".repeat(31) });
    expect(result.success).toBe(false);
  });

  it("still requires the other identity fields", () => {
    for (const field of ["firstName", "lastName", "className", "guardianName"]) {
      const result = studentSchema.safeParse({ ...valid, [field]: "" });
      expect(result.success, `${field} should be required`).toBe(false);
    }
  });
});
