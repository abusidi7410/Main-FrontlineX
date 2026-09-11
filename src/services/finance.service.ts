import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";
import type { Invoice, Payment } from "@/types";

export async function listInvoices(search = ""): Promise<Invoice[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/invoices", { query: { search } });
  const term = search.trim().toLowerCase();
  return mockDelay(
    mock.invoices.filter(
      (i) => !term || i.studentName.toLowerCase().includes(term) || i.id.includes(term),
    ),
  );
}

export async function listPayments(): Promise<Payment[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/payments");
  return mockDelay(mock.payments);
}

export interface RecordPaymentInput {
  invoiceId: string;
  amount: number;
  method: Payment["method"];
  reference?: string;
  note?: string;
}

export async function recordPayment(input: RecordPaymentInput): Promise<Payment> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/payments", { method: "POST", body: input });
  const invoice = mock.invoices.find((i) => i.id === input.invoiceId);
  const payment: Payment = {
    id: `pay_${Date.now()}`,
    invoiceId: input.invoiceId,
    studentName: invoice?.studentName ?? "—",
    amount: input.amount,
    method: input.method,
    status: input.method === "cash" ? "verified" : "pending",
    reference: input.reference || `FN-${Date.now().toString().slice(-6)}`,
    recordedBy: "You",
    createdAt: new Date().toISOString(),
  };
  if (invoice) {
    invoice.paid = Math.min(invoice.total, invoice.paid + input.amount);
    invoice.status =
      invoice.paid >= invoice.total ? "paid" : invoice.paid > 0 ? "part_paid" : "unpaid";
  }
  mock.payments.unshift(payment);
  return mockDelay(payment, 700);
}

export async function verifyPayment(id: string): Promise<Payment> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/payments/${id}/verify`, { method: "POST" });
  const payment = mock.payments.find((p) => p.id === id)!;
  payment.status = "verified";
  return mockDelay(payment, 600);
}
