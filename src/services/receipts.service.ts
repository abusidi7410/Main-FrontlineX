import { apiFetch, apiFetchBlob, type Paginated } from "@/api/client";
import type { Receipt, ReceiptSettings, ReceiptStats, ReceiptStatus } from "@/types";

export interface ReceiptListQuery {
  search?: string;
  status?: ReceiptStatus | "";
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export async function listReceipts(query: ReceiptListQuery = {}): Promise<Paginated<Receipt>> {
  // SECURITY: Backend must verify permission receipts.read and schoolId match.
  return apiFetch("/receipts", {
    query: {
      search: query.search ?? "",
      status: query.status ?? "",
      dateFrom: query.dateFrom ?? "",
      dateTo: query.dateTo ?? "",
      page: query.page ?? 1,
      pageSize: query.pageSize ?? 25,
    },
  });
}

export async function getReceipt(id: string): Promise<Receipt> {
  // SECURITY: Backend must verify permission receipts.read and schoolId match.
  return apiFetch(`/receipts/${id}`);
}

export async function issueReceipt(
  paymentId: string,
  options: { replace?: boolean } = {},
): Promise<Receipt> {
  // SECURITY: Backend must verify permission receipts.issue, schoolId match and
  // that the payment is verified. It never mutates the payment or invoice.
  return apiFetch("/receipts/issue", {
    method: "POST",
    body: { paymentId, ...(options.replace ? { replace: true } : {}) },
  });
}

export async function reprintReceipt(id: string): Promise<Receipt> {
  // SECURITY: Backend must verify permission receipts.reprint and schoolId match.
  return apiFetch(`/receipts/${id}/reprint`, { method: "POST" });
}

export async function voidReceipt(id: string, reason: string): Promise<Receipt> {
  // SECURITY: Backend must verify permission receipts.void and schoolId match.
  return apiFetch(`/receipts/${id}/void`, { method: "POST", body: { reason } });
}

/** Download the server-rendered receipt PDF; the API authorises the caller first. */
export async function downloadReceiptPdf(id: string): Promise<Blob> {
  return apiFetchBlob(`/receipts/${id}/download`);
}

export async function getReceiptStats(): Promise<ReceiptStats> {
  // SECURITY: Backend must verify permission receipts.read and schoolId match.
  return apiFetch("/receipts/stats");
}

export async function getReceiptSettings(): Promise<ReceiptSettings> {
  // SECURITY: Backend must verify permission receipts.read and schoolId match.
  return apiFetch("/receipts/settings");
}

export async function updateReceiptSettings(
  input: Partial<ReceiptSettings>,
): Promise<ReceiptSettings> {
  // SECURITY: Backend must verify permission receipts.settings and schoolId match.
  return apiFetch("/receipts/settings", { method: "PATCH", body: input });
}
