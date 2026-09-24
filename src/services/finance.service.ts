import { apiFetch } from "@/api/client";
import type { Invoice, Payment } from "@/types";

export async function listInvoices(search = ""): Promise<Invoice[]> {
  return apiFetch("/invoices", { query: { search } });
}

export async function listPayments(): Promise<Payment[]> {
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
  return apiFetch("/payments", { method: "POST", body: input });
}

export async function verifyPayment(id: string): Promise<Payment> {
  return apiFetch(`/payments/${id}/verify`, { method: "POST" });
}

export async function reversePayment(id: string): Promise<Payment> {
  return apiFetch(`/payments/${id}/reverse`, { method: "POST" });
}

export async function cancelPayment(id: string): Promise<Payment> {
  return apiFetch(`/payments/${id}/cancel`, { method: "POST" });
}

export interface FeeItem {
  label: string;
  amount: number;
  className?: string;
}

export async function getFeeStructure(): Promise<{ items: FeeItem[] }> {
  return apiFetch("/fees/structure");
}

export async function updateFeeStructure(items: FeeItem[]): Promise<{ items: FeeItem[] }> {
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
  return apiFetch("/invoices/generate", { method: "POST", body: input });
}