import { describe, expect, it } from "vitest";
import {
  normalizeNigerianPhone,
  ngPhone,
  emailField,
  passwordField,
  scoreField,
  admissionNumber,
  requiredText,
} from "@/lib/validation";

describe("normalizeNigerianPhone", () => {
  it("accepts local format 08012345678", () => {
    expect(normalizeNigerianPhone("08012345678")).toBe("+2348012345678");
  });

  it("accepts international format +2348012345678", () => {
    expect(normalizeNigerianPhone("+2348012345678")).toBe("+2348012345678");
  });

  it("accepts digits-only 2348012345678", () => {
    expect(normalizeNigerianPhone("2348012345678")).toBe("+2348012345678");
  });

  it("accepts spaced format 0801 234 5678", () => {
    expect(normalizeNigerianPhone("0801 234 5678")).toBe("+2348012345678");
  });

  it("returns null for invalid inputs", () => {
    expect(normalizeNigerianPhone("12345")).toBeNull();
    expect(normalizeNigerianPhone("abcdefghij")).toBeNull();
    expect(normalizeNigerianPhone("0801234567")).toBeNull(); // too short
    expect(normalizeNigerianPhone("080123456789")).toBeNull(); // too long
  });
});

describe("ngPhone zod schema", () => {
  it("transforms valid phone to E.164 format", () => {
    expect(ngPhone.parse("08012345678")).toBe("+2348012345678");
  });

  it("rejects invalid phone", () => {
    expect(() => ngPhone.parse("12345")).toThrow();
  });
});

describe("emailField", () => {
  it("lowercases and trims", () => {
    expect(emailField.parse("  Admin@Alnoor.edu.ng  ")).toBe("admin@alnoor.edu.ng");
  });

  it("rejects invalid emails", () => {
    expect(() => emailField.parse("not-an-email")).toThrow();
    expect(() => emailField.parse("")).toThrow();
  });
});

describe("passwordField", () => {
  it("accepts password with letters and numbers >=8 chars", () => {
    expect(passwordField.parse("nexus1234")).toBe("nexus1234");
  });

  it("rejects short passwords", () => {
    expect(() => passwordField.parse("abc1234")).toThrow();
  });

  it("rejects letters-only password (no number)", () => {
    expect(() => passwordField.parse("abcdefgh")).toThrow();
  });

  it("rejects digits-only password (no letter)", () => {
    expect(() => passwordField.parse("12345678")).toThrow();
  });
});

describe("requiredText", () => {
  const nameSchema = requiredText("Name", 50);

  it("accepts valid non-empty trimmed string", () => {
    expect(nameSchema.parse("  Kano  ")).toBe("Kano");
  });

  it("rejects empty string", () => {
    expect(() => nameSchema.parse("")).toThrow("Name is required");
  });

  it("rejects strings exceeding max length", () => {
    expect(() => nameSchema.parse("a".repeat(51))).toThrow();
  });
});

describe("scoreField", () => {
  const ca = scoreField("CA", 40);

  it("accepts valid score", () => {
    expect(ca.parse(35)).toBe(35);
    expect(ca.parse("20")).toBe(20); // coerces string
  });

  it("rejects negative", () => {
    expect(() => ca.parse(-1)).toThrow("cannot be negative");
  });

  it("rejects score above max", () => {
    expect(() => ca.parse(41)).toThrow("cannot exceed 40");
  });

  it("rejects non-numeric", () => {
    expect(() => ca.parse("abc")).toThrow("must be a number");
  });
});

describe("admissionNumber", () => {
  it("accepts valid formats", () => {
    expect(admissionNumber.parse("A123")).toBe("A123");
    expect(admissionNumber.parse("ALN/2024/001")).toBe("ALN/2024/001");
    expect(admissionNumber.parse("STU-0042")).toBe("STU-0042");
  });

  it("rejects too-short strings", () => {
    expect(() => admissionNumber.parse("A12")).toThrow();
  });

  it("rejects special characters", () => {
    expect(() => admissionNumber.parse("A123!")).toThrow();
  });
});
