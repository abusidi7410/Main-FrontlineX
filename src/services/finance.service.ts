import { apiFetch } from "@/api/client";
import type { Invoice, Payment } from "@/types";

export async function listInvoices(search = ""): Promise<Invoice[]> {
  // SECURITY: Backend must verify permission finance.read and schoolId match, or restrict students to their own invoices.
  return apiFetch("/invoices", { query: { search } });
}

export async function listPayments(): Promise<Payment[]> {
  // SECURITY: Backend must verify permission finance.read and schoolId match, or restrict students to their own payments.
  return apiFetch("/payments");
}

export interface RecordPaymentInput {
  invoiceId: string;
  amount: number;
  method: Payment["method"];
  reference?: string;
  note?: string;
}

export async function recordPayment(input: RecordPaymentInput): Promise<Payment> {
  // SECURITY: Backend must verify permission finance.write and schoolId match, or restrict self-service payment to the caller's authorized invoice.
  return apiFetch("/payments", { method: "POST", body: input });
}

export async function verifyPayment(id: string): Promise<Payment> {
  // SECURITY: Backend must verify permission finance.verify and schoolId match.
  return apiFetch(`/payments/${id}/verify`, { method: "POST" });
}

export async function reversePayment(id: string): Promise<Payment> {
  // SECURITY: Backend must verify permission finance.write and schoolId match.
  return apiFetch(`/payments/${id}/reverse`, { method: "POST" });
}

export async function cancelPayment(id: string): Promise<Payment> {
  // SECURITY: Backend must verify permission finance.write and schoolId match.
  return apiFetch(`/payments/${id}/cancel`, { method: "POST" });
}

export interface FeeItem {
  label: string;
  amount: number;
  className?: string;
}

/** Mirrors the backend `FeeStructure.FeeType` vocabulary. */
export const FEE_TYPES = [
  "registration",
  "tuition",
  "development",
  "ict",
  "uniform",
  "exam",
  "transport",
  "meals",
  "other",
] as const;

export type FeeType = (typeof FEE_TYPES)[number];

/**
 * `WHOLE_SESSION` is stored as an empty term string, which the backend reads as
 * "applies to every term" (`FeeStructure.term` is blank for session-wide fees).
 * A Radix `Select` cannot hold an empty item value, so the UI selects
 * `ALL_TERMS` and `toTerm()` converts it on the way to the API.
 */
export const WHOLE_SESSION = "";
export const ALL_TERMS = "__all__";

export const FEE_TERMS = [
  { value: ALL_TERMS, label: "Whole session" },
  { value: "First Term", label: "First term only" },
  { value: "Second Term", label: "Second term only" },
  { value: "Third Term", label: "Third term only" },
] as const;

/** Select value -> the term string the API stores. */
export function toTerm(selectValue: string): string {
  return selectValue === ALL_TERMS ? WHOLE_SESSION : selectValue;
}

/** The term string the API stores -> its select value. */
export function toTermValue(term: string): string {
  return term === WHOLE_SESSION ? ALL_TERMS : term;
}

/** Two lines collide if they share a fee type and a term. */
export function isDuplicateFee(fee: LevelFee, others: LevelFee[], ignoreIndex?: number): boolean {
  return others.some(
    (other, index) =>
      index !== ignoreIndex && other.feeType === fee.feeType && other.term === fee.term,
  );
}

export const FEE_TYPE_LABELS: Record<FeeType, string> = {
  registration: "Registration",
  tuition: "Tuition",
  development: "Development",
  ict: "ICT",
  uniform: "Uniform",
  exam: "Examination",
  transport: "Transport",
  meals: "Meals",
  other: "Other",
};

export interface LevelFee {
  id?: number;
  feeType: FeeType;
  label: string;
  amount: number;
  term: string;
  isRequired: boolean;
}

export interface LevelFeeStructure {
  id: number;
  code: string;
  name: string;
  fees: LevelFee[];
}

export interface FeeStructure {
  /** Legacy school-wide list. Still returned for schools that predate per-level fees. */
  items: FeeItem[];
  levels: LevelFeeStructure[];
}

export async function getFeeStructure(): Promise<FeeStructure> {
  // SECURITY: Backend must verify permission finance.read and schoolId match.
  return apiFetch("/fees/structure");
}

export interface SaveLevelFeesResult {
  levels: LevelFeeStructure[];
  items: FeeItem[];
  invoicedPendingStudents: number;
  invoicedPendingStudentsByLevel: Record<string, number>;
}

/**
 * Save one level's Payment Structure. Every other level is left untouched.
 * SECURITY: Backend must verify permission finance.structure and schoolId match.
 */
export async function saveLevelFees(
  levelId: number,
  fees: LevelFee[],
): Promise<SaveLevelFeesResult> {
  return apiFetch("/fees/structure", { method: "PUT", body: { levels: [{ levelId, fees }] } });
}

export async function updateFeeStructure(
  items: FeeItem[],
): Promise<{ items: FeeItem[]; invoicedPendingStudents: number }> {
  // SECURITY: Backend must verify permission finance.structure and schoolId match.
  // Saving also invoices any students who registered before a fee structure
  // existed, since the bulk generator only bills active students and those
  // students would otherwise never be able to pay their way in.
  return apiFetch("/fees/structure", { method: "PUT", body: { items } });
}

export interface GenerateInvoicesInput {
  className: string;
  term: string;
  overwrite?: boolean;
}

export async function generateInvoices(
  input: GenerateInvoicesInput,
): Promise<{ generated: number; updated: number; totalStudents: number; term: string }> {
  // SECURITY: Backend must verify permission finance.write and schoolId match.
  return apiFetch("/invoices/generate", { method: "POST", body: input });
}
