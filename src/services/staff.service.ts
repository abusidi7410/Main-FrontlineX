import { apiFetch } from "@/api/client";
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
  return apiFetch("/staff");
}

export async function getStaffMember(id: string): Promise<StaffMember> {
  return apiFetch(`/staff/${id}`);
}

export async function createStaff(input: StaffInput): Promise<StaffMember> {
  return apiFetch("/staff", { method: "POST", body: input });
}

export async function updateStaff(id: string, input: StaffInput): Promise<StaffMember> {
  return apiFetch(`/staff/${id}`, { method: "PATCH", body: input });
}

export async function suspendStaff(id: string): Promise<StaffMember> {
  return apiFetch(`/staff/${id}`, { method: "PATCH", body: { status: "suspended" } });
}

export async function reinstateStaff(id: string): Promise<StaffMember> {
  return apiFetch(`/staff/${id}`, { method: "PATCH", body: { status: "active" } });
}

export async function inviteStaff(id: string): Promise<StaffMember> {
  return apiFetch(`/staff/${id}/invite`, { method: "POST" });
}

export async function setStaffClasses(id: string, classes: string[]): Promise<StaffMember> {
  return apiFetch(`/staff/${id}`, { method: "PATCH", body: { classes } });
}

export async function deleteStaff(id: string): Promise<void> {
  return apiFetch(`/staff/${id}`, { method: "DELETE" });
}