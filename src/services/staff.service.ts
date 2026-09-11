import { USE_MOCK_ADAPTER, apiFetch, mockDelay } from "@/api/client";
import * as mock from "@/api/mock";
import type { StaffMember } from "@/types";

export type StaffRole = "teacher" | "accountant" | "secretary" | "principal";

export interface StaffInput {
  fullName: string;
  email: string;
  phone: string;
  role: StaffRole;
  subjects: string[];
  classes: string[];
}

export async function listStaff(): Promise<StaffMember[]> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/staff");
  return mockDelay(mock.staff);
}

export async function getStaffMember(id: string): Promise<StaffMember> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/staff/${id}`);
  const found = mock.staff.find((m) => m.id === id);
  if (!found) throw new Error("We couldn't find that staff member.");
  return mockDelay(found, 350);
}

function findStaffMember(id: string): StaffMember {
  const found = mock.staff.find((m) => m.id === id);
  if (!found) throw new Error("We couldn't find that staff member.");
  return found;
}

export async function createStaff(input: StaffInput): Promise<StaffMember> {
  if (!USE_MOCK_ADAPTER) return apiFetch("/staff", { method: "POST", body: input });
  const created: StaffMember = {
    ...input,
    id: `stf_${Date.now()}`,
    status: "invited",
  };
  mock.staff.unshift(created);
  return mockDelay(created, 650);
}

export async function updateStaff(id: string, input: StaffInput): Promise<StaffMember> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/staff/${id}`, { method: "PATCH", body: input });
  const member = findStaffMember(id);
  const role = input.role as StaffMember["role"];
  Object.assign(member, {
    fullName: input.fullName,
    email: input.email,
    phone: input.phone,
    role,
    subjects: role === "teacher" ? input.subjects : [],
    classes: role === "teacher" ? input.classes : [],
  });
  return mockDelay(member, 650);
}

export async function suspendStaff(id: string): Promise<StaffMember> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/staff/${id}`, { method: "PATCH", body: { status: "suspended" } });
  const member = findStaffMember(id);
  member.status = "suspended";
  return mockDelay(member, 500);
}

export async function reinstateStaff(id: string): Promise<StaffMember> {
  if (!USE_MOCK_ADAPTER)
    return apiFetch(`/staff/${id}`, { method: "PATCH", body: { status: "active" } });
  const member = findStaffMember(id);
  member.status = "active";
  return mockDelay(member, 500);
}

export async function inviteStaff(id: string): Promise<StaffMember> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/staff/${id}/invite`, { method: "POST" });
  const member = findStaffMember(id);
  member.status = "invited";
  return mockDelay(member, 500);
}

export async function setStaffClasses(id: string, classes: string[]): Promise<StaffMember> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/staff/${id}`, { method: "PATCH", body: { classes } });
  const member = findStaffMember(id);
  member.classes = classes;
  return mockDelay(member, 550);
}

export async function deleteStaff(id: string): Promise<void> {
  if (!USE_MOCK_ADAPTER) return apiFetch(`/staff/${id}`, { method: "DELETE" });
  const index = mock.staff.findIndex((m) => m.id === id);
  if (index < 0) throw new Error("We couldn't find that staff member.");
  mock.staff.splice(index, 1);
  return mockDelay(undefined, 600);
}
