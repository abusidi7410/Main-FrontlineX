import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";
import type { PlatformSchool } from "@/types";

export async function listPlatformSchools(search = "", status = ""): Promise<PlatformSchool[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/platform/schools", { query: { search, status } });
  const term = search.trim().toLowerCase();
  return mockDelay(
    mock.platformSchools.filter(
      (s) =>
        (!term || s.name.toLowerCase().includes(term) || s.state.toLowerCase().includes(term)) &&
        (!status || s.status === status),
    ),
  );
}

export async function setSchoolStatus(
  id: string,
  status: PlatformSchool["status"],
): Promise<PlatformSchool> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/platform/schools/${id}/status`, { method: "PATCH", body: { status } });
  const school = mock.platformSchools.find((s) => s.id === id)!;
  school.status = status;
  return mockDelay(school, 500);
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
  if (!USE_MOCK_ADAPTER) return apiFetch("/platform/audit");
  const actions = [
    ["Published results", "JSS 2A Mathematics", "info"],
    ["Suspended school", "Hilltop College", "critical"],
    ["Verified bank transfer", "FN-83021", "info"],
    ["Failed sign-in attempt", "admin@greenfield.edu.ng", "warning"],
    ["Changed subscription tier", "Royal Crest Academy", "warning"],
    ["Exported student list", "Al-Noor Model Academy", "info"],
  ] as const;
  return mockDelay(
    actions.map((a, i) => ({
      id: `aud_${i}`,
      actor: i % 2 ? "ops@frontlinenexus.com" : "admin@alnoor.edu.ng",
      action: a[0],
      target: a[1],
      severity: a[2],
      ip: `102.89.${20 + i}.${100 + i}`,
      createdAt: new Date(Date.now() - i * 5400_000).toISOString(),
    })),
  );
}
