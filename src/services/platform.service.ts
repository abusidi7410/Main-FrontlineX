import { apiFetch } from "@/api/client";
import type { PlatformSchool } from "@/types";

export async function listPlatformSchools(search = "", status = ""): Promise<PlatformSchool[]> {
  return apiFetch("/platform/schools", { query: { search, status } });
}

export async function setSchoolStatus(
  id: string,
  status: PlatformSchool["status"],
): Promise<PlatformSchool> {
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

export async function createPlatformSchool(
  input: CreatePlatformSchoolInput,
): Promise<PlatformSchoolDetail> {
  return apiFetch("/platform/schools", { method: "POST", body: input });
}

export async function getPlatformSchool(id: string): Promise<PlatformSchoolDetail> {
  return apiFetch(`/platform/schools/${id}`);
}

export async function updatePlatformSchool(
  id: string,
  input: UpdatePlatformSchoolInput,
): Promise<PlatformSchoolDetail> {
  return apiFetch(`/platform/schools/${id}`, { method: "PATCH", body: input });
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
  return apiFetch("/platform/support/tickets");
}

export async function createSupportTicket(input: {
  schoolId?: string;
  requester: string;
  subject: string;
  message?: string;
}): Promise<PlatformTicket> {
  return apiFetch("/platform/support/tickets", { method: "POST", body: input });
}

export async function setSupportTicketStatus(
  id: string,
  status: PlatformTicket["status"],
): Promise<PlatformTicket> {
  return apiFetch(`/platform/support/tickets/${id}/status`, { method: "POST", body: { status } });
}

export interface PlatformBroadcast {
  id: string;
  title: string;
  body: string;
  audience: string[];
  createdAt: string;
  author: string;
}

export async function listBroadcasts(): Promise<PlatformBroadcast[]> {
  return apiFetch("/platform/support/announcements");
}

export async function createBroadcast(title: string, body: string): Promise<PlatformBroadcast> {
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
  return apiFetch("/platform/audit");
}
