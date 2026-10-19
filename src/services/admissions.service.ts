import { apiFetch, apiFetchBlob, type Paginated } from "@/api/client";
import type {
  AdmissionApplication,
  AdmissionApplicationInput,
  AdmissionApprovalResult,
  AdmissionDocument,
  AdmissionDocumentCategory,
  AdmissionSettings,
  AdmissionStats,
  AdmissionStatus,
} from "@/types";

export interface AdmissionListQuery {
  search?: string;
  status?: AdmissionStatus | "";
  classId?: number | "";
  page?: number;
  pageSize?: number;
}

export async function listAdmissionApplications(
  query: AdmissionListQuery = {},
): Promise<Paginated<AdmissionApplication>> {
  // SECURITY: Backend must verify permission admissions.read and schoolId match.
  return apiFetch("/admissions/applications", {
    query: {
      search: query.search ?? "",
      status: query.status ?? "",
      classId: query.classId ?? "",
      page: query.page ?? 1,
      pageSize: query.pageSize ?? 25,
    },
  });
}

export async function getAdmissionApplication(id: string): Promise<AdmissionApplication> {
  // SECURITY: Backend must verify permission admissions.read and schoolId match.
  return apiFetch(`/admissions/applications/${id}`);
}

export async function createAdmissionApplication(
  input: AdmissionApplicationInput,
): Promise<AdmissionApplication> {
  // SECURITY: Backend must verify permission admissions.write and schoolId match.
  return apiFetch("/admissions/applications", { method: "POST", body: input });
}

export async function updateAdmissionApplication(
  id: string,
  input: AdmissionApplicationInput,
): Promise<AdmissionApplication> {
  // SECURITY: Backend must verify permission admissions.write and schoolId match.
  return apiFetch(`/admissions/applications/${id}`, { method: "PATCH", body: input });
}

export async function deleteAdmissionApplication(id: string): Promise<void> {
  // SECURITY: Backend must verify permission admissions.write, schoolId match and draft status.
  return apiFetch(`/admissions/applications/${id}`, { method: "DELETE" });
}

export async function submitAdmissionApplication(
  id: string,
  options: { allowDuplicate?: boolean } = {},
): Promise<AdmissionApplication> {
  // SECURITY: Backend must verify permission admissions.write and schoolId match.
  return apiFetch(`/admissions/applications/${id}/submit`, {
    method: "POST",
    body: { allowDuplicate: options.allowDuplicate ?? false },
  });
}

export async function startAdmissionReview(id: string): Promise<AdmissionApplication> {
  // SECURITY: Backend must verify permission admissions.review and schoolId match.
  return apiFetch(`/admissions/applications/${id}/start-review`, { method: "POST" });
}

export async function approveAdmissionApplication(
  id: string,
  options: { classId?: number | null; admissionNumber?: string } = {},
): Promise<AdmissionApprovalResult> {
  // SECURITY: Backend must verify permission admissions.review and schoolId match.
  return apiFetch(`/admissions/applications/${id}/approve`, {
    method: "POST",
    body: {
      ...(options.classId ? { classId: options.classId } : {}),
      ...(options.admissionNumber ? { admissionNumber: options.admissionNumber } : {}),
    },
  });
}

export async function rejectAdmissionApplication(
  id: string,
  reason: string,
): Promise<AdmissionApplication> {
  // SECURITY: Backend must verify permission admissions.review and schoolId match.
  return apiFetch(`/admissions/applications/${id}/reject`, {
    method: "POST",
    body: { reason },
  });
}

export async function withdrawAdmissionApplication(
  id: string,
  reason = "",
): Promise<AdmissionApplication> {
  // SECURITY: Backend must verify permission admissions.write and schoolId match.
  return apiFetch(`/admissions/applications/${id}/withdraw`, {
    method: "POST",
    body: { reason },
  });
}

export async function listAdmissionDocuments(id: string): Promise<AdmissionDocument[]> {
  // SECURITY: Backend must verify permission admissions.read and schoolId match.
  return apiFetch(`/admissions/applications/${id}/documents`);
}

export async function uploadAdmissionDocument(
  id: string,
  input: { category: AdmissionDocumentCategory; file: File },
): Promise<AdmissionDocument> {
  // SECURITY: Backend must verify permission admissions.write, schoolId match and
  // sniff the file's magic bytes; no client-supplied path is trusted.
  const body = new FormData();
  body.append("category", input.category);
  body.append("file", input.file);
  return apiFetch(`/admissions/applications/${id}/documents`, { method: "POST", body });
}

export async function deleteAdmissionDocument(documentId: string): Promise<void> {
  // SECURITY: Backend must verify permission admissions.write and schoolId match.
  return apiFetch(`/admissions/documents/${documentId}`, { method: "DELETE" });
}

export async function reviewAdmissionDocument(
  documentId: string,
  input: { status: "verified" | "rejected"; note?: string | undefined },
): Promise<AdmissionDocument> {
  // SECURITY: Backend must verify permission admissions.review and schoolId match.
  return apiFetch(`/admissions/documents/${documentId}/review`, {
    method: "POST",
    body: { status: input.status, note: input.note ?? "" },
  });
}

/** Download a private document; the API authorises the caller first. */
export async function downloadAdmissionDocument(documentId: string): Promise<Blob> {
  return apiFetchBlob(`/admissions/documents/${documentId}/download`);
}

export async function getAdmissionStats(): Promise<AdmissionStats> {
  // SECURITY: Backend must verify permission admissions.read and schoolId match.
  return apiFetch("/admissions/stats");
}

export async function getAdmissionSettings(): Promise<AdmissionSettings> {
  // SECURITY: Backend must verify permission admissions.read and schoolId match.
  return apiFetch("/admissions/settings");
}

export async function updateAdmissionSettings(
  input: Partial<AdmissionSettings>,
): Promise<AdmissionSettings> {
  // SECURITY: Backend must verify permission admissions.settings and schoolId match.
  return apiFetch("/admissions/settings", { method: "PATCH", body: input });
}
