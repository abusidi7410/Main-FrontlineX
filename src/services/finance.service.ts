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