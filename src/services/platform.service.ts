import { apiFetch } from "@/api/client";
import type { Announcement, PlatformOverview, PlatformOverviewRange, PlatformSchool } from "@/types";

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
}

export async function listAuditEvents(): Promise<AuditEvent[]> {
  // SECURITY: Backend must verify permission audit.read and the platform-manager role; schoolId match is intentionally not required for this global audit scope.
  return apiFetch("/platform/audit");
}
