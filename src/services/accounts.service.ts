import { apiFetch, type Paginated } from "@/api/client";
import type { AccountCreateInput, AccountStats, DefaultCredentials, SchoolAccount } from "@/types";

export interface AccountQuery {
  search?: string;
  role?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

export async function listAccounts(query: AccountQuery = {}): Promise<Paginated<SchoolAccount>> {
  return apiFetch("/accounts/users", { query: { ...query } });
}

export async function getAccountStats(): Promise<AccountStats> {
  return apiFetch("/accounts/users/stats");
}

export interface CreatedAccount extends SchoolAccount {
  defaultCredentials?: DefaultCredentials;
}

export async function createAccount(input: AccountCreateInput): Promise<CreatedAccount> {
  return apiFetch("/accounts/users", { method: "POST", body: input });
}

export async function updateAccount(
  id: string,
  input: Partial<Pick<AccountCreateInput, "fullName" | "phone" | "role">>,
): Promise<SchoolAccount> {
  return apiFetch(`/accounts/users/${id}`, { method: "PATCH", body: input });
}

export async function deleteAccount(id: string): Promise<void> {
  return apiFetch(`/accounts/users/${id}`, { method: "DELETE" });
}

export async function resetAccountPassword(
  id: string,
): Promise<{ defaultCredentials: DefaultCredentials }> {
  return apiFetch(`/accounts/users/${id}/reset-password`, { method: "POST" });
}

export async function setAccountStatus(
  id: string,
  status: "active" | "inactive",
): Promise<SchoolAccount> {
  const action = status === "active" ? "activate" : "deactivate";
  return apiFetch(`/accounts/users/${id}/${action}`, { method: "POST" });
}
