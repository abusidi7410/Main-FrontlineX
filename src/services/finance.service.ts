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

export async function getFeeStructure(): Promise<{ items: FeeItem[] }> {
  // SECURITY: Backend must verify permission finance.read and schoolId match.
  return apiFetch("/fees/structure");
}

export async function updateFeeStructure(items: FeeItem[]): Promise<{ items: FeeItem[] }> {
  // SECURITY: Backend must verify permission finance.write and schoolId match.
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
