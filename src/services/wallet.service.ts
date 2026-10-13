import { apiFetch } from "@/api/client";

export interface WalletSmsGate {
  globalEnabled: boolean;
  platformBlocked: boolean;
  schoolEnabled: boolean;
  balanceKobo: number;
  priceKobo: number;
  canSend: boolean;
}

export interface WalletOverview {
  balanceKobo: number;
  balance: number;
  studentPriceKobo: number;
  studentPrice: number;
  smsPriceKobo: number;
  smsPrice: number;
  graceDays: number;
  autoRenew: boolean;
  minDepositKobo: number;
  minDeposit: number;
  maxDepositKobo: number | null;
  sms: WalletSmsGate;
}

export interface WalletTx {
  id: number;
  reference: string;
  direction: "credit" | "debit";
  amount_kobo: number;
  category: string;
  status: string;
  message_reference: string;
  provider_reference: string;
  balance_before_kobo: number;
  balance_after_kobo: number;
  description: string;
  created_at: string;
  studentName: string;
  admissionNumber: string;
}

export type StudentAccessStatus =
  "Active" | "ExpiringSoon" | "GracePeriod" | "Expired" | "NeverActivated";

export interface StudentAccess {
  studentId: string;
  studentName: string;
  admissionNumber: string;
  status: StudentAccessStatus;
  priceKobo: number;
  periodStart: string | null;
  periodEnd: string | null;
  amountKobo: number | null;
}

export interface DepositCheckout {
  reference: string;
  amountKobo: number;
  amount: number;
  currency: string;
  email: string;
  accessCode: string;
  authorizationUrl: string;
  publicKey: string;
}

export interface DepositVerification {
  status: "success" | "failed";
  reference: string;
  balanceKobo?: number;
}

export interface SmsAlert {
  id: number;
  reference: string;
  recipient: string;
  message: string;
  status: string;
  customer_kobo: number;
  provider_cost_kobo: number | null;
  provider_reference: string;
  provider_error: string;
  created_at: string;
}

export const ACCESS_STATUS_LABEL: Record<StudentAccessStatus, string> = {
  Active: "Active",
  ExpiringSoon: "Expiring soon",
  GracePeriod: "Grace period",
  Expired: "Expired",
  NeverActivated: "Needs activation",
};

export async function getWallet(): Promise<WalletOverview> {
  return apiFetch("/billing/wallet");
}

export async function listWalletTransactions(
  page = 1,
  pageSize = 20,
  category?: string,
): Promise<{ results: WalletTx[]; count: number; page: number; pageSize: number }> {
  return apiFetch("/billing/transactions", {
    query: { page, pageSize, ...(category ? { category } : {}) },
  });
}

export async function startDeposit(amountKobo: number): Promise<DepositCheckout> {
  return apiFetch("/billing/deposits", { method: "POST", body: { amountKobo } });
}

export async function verifyDeposit(reference: string): Promise<DepositVerification> {
  return apiFetch(`/billing/deposits/verify/${encodeURIComponent(reference)}`);
}

export async function listStudentAccess(
  search?: string,
  page = 1,
  pageSize = 20,
): Promise<{
  results: StudentAccess[];
  count: number;
  page: number;
  pageSize: number;
  summary: { active: number; needAttention: number; expiringSoon: number; gracePeriod: number };
}> {
  return apiFetch("/billing/students", {
    query: { ...(search ? { search } : {}), page, pageSize },
  });
}

export async function activateStudent(studentId: string): Promise<{
  created: boolean;
  periodStart: string;
  periodEnd: string;
  amountKobo: number;
  status: StudentAccessStatus;
}> {
  return apiFetch(`/billing/students/${encodeURIComponent(studentId)}/activate`, {
    method: "POST",
  });
}

export async function getMessaging(): Promise<
  WalletSmsGate & { schoolEnabled: boolean; platformBlocked: boolean }
> {
  return apiFetch("/billing/messaging");
}

export async function setSchoolMessaging(
  enabled: boolean,
): Promise<WalletSmsGate & { schoolEnabled: boolean; platformBlocked: boolean }> {
  return apiFetch("/billing/messaging", { method: "PATCH", body: { schoolEnabled: enabled } });
}

export async function sendAlert(input: {
  recipient: string;
  message: string;
  reference?: string;
}): Promise<SmsAlert> {
  return apiFetch("/billing/alerts", { method: "POST", body: input });
}

export async function listAlerts(
  page = 1,
  pageSize = 20,
): Promise<{ results: SmsAlert[]; count: number; page: number; pageSize: number }> {
  return apiFetch("/billing/alerts/history", { query: { page, pageSize } });
}
