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