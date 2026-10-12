import { apiFetch } from "@/api/client";
import type {
  Announcement,
  PlatformOverview,
  PlatformOverviewRange,
  PlatformSchool,
} from "@/types";

export async function getPlatformOverview(
  range: PlatformOverviewRange = "30d",
): Promise<PlatformOverview> {
  return apiFetch("/platform/overview", { query: { range } });
}

export async function listPlatformSchools(search = "", status = ""): Promise<PlatformSchool[]> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch("/platform/schools", { query: { search, status } });
}

export async function setSchoolStatus(
  id: string,
  status: PlatformSchool["status"],
): Promise<PlatformSchool> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch(`/platform/schools/${id}/status`, { method: "PATCH", body: { status } });
}

export interface PlatformSchoolDetail extends PlatformSchool {
  slug: string;
  schoolType: string;
  address: string;
  lga: string;
  phone: string;
  email: string;
  website: string;
  primaryColor: string;
  secondaryColor: string;
  currentSession: string;
  currentTerm: string;
  isActive: boolean;
  studentCount: number;
  staffCount: number;
  // Subscription facts (from `_subscription_json` on the backend).
  planId: string | null;
  planName: string;
  monthlyPrice: number;
  expiresAt: string | null;
  overrideActive: boolean;
  overrideUntil: string | null;
  overrideNote: string;
  overrideReason: string;
  overrideBy: string | null;
  overrideAt: string | null;
  tierLabel?: string;
}

export interface CreatePlatformSchoolInput {
  name: string;
  schoolType: string;
  address: string;
  state: string;
  lga: string;
  phone: string;
  email: string;
  website?: string;
  tierId?: string;
  currentSession?: string;
  currentTerm?: string;
  primaryColor?: string;
  secondaryColor?: string;
}

export type UpdatePlatformSchoolInput = Partial<CreatePlatformSchoolInput>;

export interface PlatformSchoolCredentials {
  email: string;
  password: string;
  mustChangePassword?: boolean;
}

export interface RegisterSchoolResponse extends PlatformSchoolDetail {
  defaultCredentials?: PlatformSchoolCredentials;
}

export async function createPlatformSchool(
  input: CreatePlatformSchoolInput,
): Promise<RegisterSchoolResponse> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required when creating a new tenant.
  return apiFetch("/platform/schools", { method: "POST", body: input });
}

export async function getPlatformSchool(id: string): Promise<PlatformSchoolDetail> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch(`/platform/schools/${id}`);
}

export async function updatePlatformSchool(
  id: string,
  input: UpdatePlatformSchoolInput,
): Promise<PlatformSchoolDetail> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch(`/platform/schools/${id}`, { method: "PATCH", body: input });
}

export interface DeleteSchoolResult {
  detail: string;
  deleted: string;
  remaining: number;
}

export async function deletePlatformSchool(
  id: string,
  confirm: string,
): Promise<DeleteSchoolResult> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch(`/platform/schools/${id}`, { method: "DELETE", body: { confirm } });
}

export interface PlatformTicket {
  id: string;
  school: string;
  subject: string;
  requester: string;
  status: "pending" | "under_review" | "verified";
  createdAt: string;
}

export async function listSupportTickets(): Promise<PlatformTicket[]> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch("/platform/support/tickets");
}

export async function createSupportTicket(input: {
  schoolId?: string;
  requester: string;
  subject: string;
  message?: string;
}): Promise<PlatformTicket> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch("/platform/support/tickets", { method: "POST", body: input });
}

export async function setSupportTicketStatus(
  id: string,
  status: PlatformTicket["status"],
): Promise<PlatformTicket> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch(`/platform/support/tickets/${id}/status`, { method: "POST", body: { status } });
}

/**
 * A broadcast is the same wire shape as a school announcement — the platform
 * endpoint and the school board now share one serialiser — so it is aliased
 * rather than redeclared. Two copies of one shape is how they drift.
 */
export type PlatformBroadcast = Announcement;

export async function listBroadcasts(): Promise<PlatformBroadcast[]> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch("/platform/support/announcements");
}

export async function createBroadcast(title: string, body: string): Promise<PlatformBroadcast> {
  // SECURITY: Backend must verify permission platform.manage; schoolId match is intentionally not required for this cross-school platform scope.
  return apiFetch("/platform/support/announcements", { method: "POST", body: { title, body } });
}

export interface AuditEvent {
  id: string;
  actor: string;
  action: string;
  target: string;
  ip: string;
  createdAt: string;
  severity: "info" | "warning" | "critical";
  role?: string;
  school?: string;
  schoolId?: string | null;
}

interface PaginatedResponse<T> {
  results: T[];
  count: number;
  page: number;
  pageSize: number;
}

function unwrapList<T>(payload: T[] | PaginatedResponse<T>): T[] {
  return Array.isArray(payload) ? payload : (payload?.results ?? []);
}

export async function listAuditEvents(params?: {
  action?: string;
  severity?: string;
  actor?: string;
  search?: string;
  schoolId?: string;
}): Promise<AuditEvent[]> {
  // SECURITY: Backend must verify permission audit.read and the platform-manager role; schoolId match is intentionally not required for this global audit scope.
  const payload = await apiFetch<AuditEvent[] | PaginatedResponse<AuditEvent>>("/platform/audit", {
    query: { ...(params ?? {}) },
  });
  return unwrapList(payload);
}

// ── Subscription plans ──────────────────────────────────────────────

export interface PlatformPlan {
  id: string | null;
  label: string;
  description?: string;
  billingInterval?: string;
  trialDays?: number;
  currency?: string;
  minStudents: number;
  maxStudents: number | null;
  monthlyPrice: string | number;
  aiCredits?: number;
  storageGb?: number;
  smsAllowance?: number;
  otpAllowance?: number;
  aiAllowance?: number;
  smsCostPerUnit?: number;
  otpCostPerUnit?: number;
  aiCostPerCredit?: number;
  sortOrder?: number;
  isActive?: boolean;
  features?: string[];
}

export async function listPlatformPlans(): Promise<PlatformPlan[]> {
  const payload = await apiFetch<{ results: PlatformPlan[] } | PlatformPlan[]>("/platform/plans");
  if (Array.isArray(payload)) return payload;
  return payload.results ?? [];
}

export async function createPlatformPlan(input: Partial<PlatformPlan>): Promise<PlatformPlan> {
  return apiFetch("/platform/plans", { method: "POST", body: input });
}

export async function updatePlatformPlan(
  pk: number | string,
  input: Partial<PlatformPlan>,
): Promise<PlatformPlan> {
  return apiFetch(`/platform/plans/${pk}`, { method: "PATCH", body: input });
}

export async function deletePlatformPlan(pk: number | string): Promise<{ deleted: string }> {
  return apiFetch(`/platform/plans/${pk}`, { method: "DELETE" });
}

// ── Per-school subscription (lifecycle + complimentary access) ──────

export interface UpdateSubscriptionInput {
  planId?: string | undefined;
  status?: string | undefined;
  expiresAt?: string | null | undefined;
  extendDays?: number | undefined;
  overrideActive?: boolean | undefined;
  overrideUntil?: string | null | undefined;
  note?: string | undefined;
  reason?: string | undefined;
}

export async function updateSchoolSubscription(
  id: string,
  input: UpdateSubscriptionInput,
): Promise<PlatformSchoolDetail> {
  return apiFetch(`/platform/schools/${id}/subscription`, { method: "PATCH", body: input });
}

// ── Payments & revenue ──────────────────────────────────────────────

export interface SubscriptionPayment {
  id: string;
  schoolId: string;
  schoolName: string;
  planId: string | null;
  planName: string;
  reference: string;
  amount: number;
  amountKobo: number;
  currency: string;
  status: "pending" | "success" | "failed" | "abandoned";
  purpose: string;
  channel: string;
  paystackReference: string;
  paidAt: string | null;
  createdAt: string;
}

export async function listSubscriptionPayments(params?: {
  status?: string;
  schoolId?: string;
  search?: string;
}): Promise<SubscriptionPayment[]> {
  const payload = await apiFetch<SubscriptionPayment[] | PaginatedResponse<SubscriptionPayment>>(
    "/platform/subscriptions/payments",
    { query: { ...(params ?? {}) } },
  );
  return unwrapList(payload);
}

export async function getPlatformProfit(month?: string): Promise<Record<string, unknown>> {
  return apiFetch("/platform/profit", { query: { month } });
}

// ── Platform settings ───────────────────────────────────────────────

export interface PlatformSettings {
  trialDays: number;
  subscriptionPeriodDays: number;
  gracePeriodDays: number;
  supportEmail: string;
  maintenanceMessage: string;
  updatedAt: string | null;
}

export async function getPlatformSettings(): Promise<PlatformSettings> {
  return apiFetch("/platform/settings");
}

export async function updatePlatformSettings(
  input: Partial<PlatformSettings>,
): Promise<PlatformSettings> {
  return apiFetch("/platform/settings", { method: "PATCH", body: input });
}

// ── Wallet billing policy & messaging ─────────────────────────────

export interface BillingPricing {
  studentPriceKobo: number;
  smsPriceKobo: number;
  graceDays: number;
  autoRenew: boolean;
  smsEnabledGlobal: boolean;
  minDepositKobo: number;
  maxDepositKobo: number | null;
  priceChangedAt: string | null;
}

export async function getBillingPricing(): Promise<BillingPricing> {
  return apiFetch("/billing/platform/pricing");
}

export async function updateBillingPricing(
  input: Partial<BillingPricing>,
): Promise<BillingPricing> {
  return apiFetch("/billing/platform/pricing", { method: "PATCH", body: input });
}

export interface SchoolMessagingState {
  schoolId: string;
  schoolName: string;
  platformBlocked: boolean;
  schoolEnabled: boolean;
  globalEnabled: boolean;
  balanceKobo: number;
  priceKobo: number;
  canSend: boolean;
  usage: {
    total: number;
    sent: number;
    failed: number;
    refunded: number;
    chargedKobo: number;
  };
}

export async function getSchoolMessaging(schoolId: string): Promise<SchoolMessagingState> {
  return apiFetch(`/billing/platform/schools/${schoolId}/messaging`);
}

export async function updateSchoolMessaging(
  schoolId: string,
  input: { platformBlocked?: boolean; schoolEnabled?: boolean },
): Promise<SchoolMessagingState> {
  return apiFetch(`/billing/platform/schools/${schoolId}/messaging`, {
    method: "PATCH",
    body: input,
  });
}

export async function getMessagingOverview(): Promise<{
  alerts: {
    total: number;
    sent: number;
    failed: number;
    chargedKobo: number;
    knownCostKobo: number;
    unknownCostCount: number;
  };
  providerUsage: { total: number; succeeded: number; failed: number; exhausted: number };
  globalEnabled: boolean;
}> {
  return apiFetch("/billing/platform/messaging");
}

export async function createManualAdjustment(input: {
  schoolId: string;
  amountKobo: number;
  reason: string;
}): Promise<{ reference: string; balanceKobo: number }> {
  return apiFetch("/billing/platform/adjustments", { method: "POST", body: input });
}

// ── School users & read-only impersonation ──────────────────────────

export interface PlatformSchoolUser {
  id: string;
  name: string;
  email: string;
  phone: string;
  role: string;
  isActive: boolean;
  isVerified: boolean;
  mustChangePassword: boolean;
  lastLogin: string | null;
}

export async function listPlatformSchoolUsers(schoolId: string): Promise<PlatformSchoolUser[]> {
  return apiFetch(`/platform/schools/${schoolId}/users`);
}
