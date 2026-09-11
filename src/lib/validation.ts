import { z } from "zod";

/** Accepts 08012345678, 2348012345678, +2348012345678, 0801 234 5678. */
export function normalizeNigerianPhone(input: string): string | null {
  const digits = input.replace(/[^\d+]/g, "").replace(/^\+/, "");
  let local: string | null = null;
  if (/^0[789][01]\d{8}$/.test(digits)) local = digits;
  else if (/^234[789][01]\d{8}$/.test(digits)) local = `0${digits.slice(3)}`;
  return local ? `+234${local.slice(1)}` : null;
}

export const ngPhone = z
  .string()
  .trim()
  .min(1, { message: "Phone number is required" })
  .refine((v) => normalizeNigerianPhone(v) !== null, {
    message: "Enter a valid Nigerian phone number, e.g. 08012345678",
  })
  .transform((v) => normalizeNigerianPhone(v)!);

export const emailField = z
  .string()
  .trim()
  .min(1, { message: "Email address is required" })
  .email({ message: "Enter a valid email address" })
  .max(255)
  .transform((v) => v.toLowerCase());

export const passwordField = z
  .string()
  .min(8, { message: "Use at least 8 characters" })
  .max(72, { message: "Password is too long" })
  .refine((v) => /[A-Za-z]/.test(v) && /\d/.test(v), {
    message: "Include at least one letter and one number",
  });

export const requiredText = (label: string, max = 120) =>
  z
    .string()
    .trim()
    .min(1, { message: `${label} is required` })
    .max(max, { message: `${label} must be under ${max} characters` });

export const scoreField = (label: string, max: number) =>
  z.coerce
    .number({ invalid_type_error: `${label} must be a number` })
    .min(0, { message: `${label} cannot be negative` })
    .max(max, { message: `${label} cannot exceed ${max}` });

export const admissionNumber = z
  .string()
  .trim()
  .regex(/^[A-Za-z0-9/-]{4,20}$/, { message: "Use 4–20 letters, numbers, / or -" });
