import type { QueryClient, QueryKey } from "@tanstack/react-query";

/**
 * Cache prefixes for every screen whose data is derived from the authoritative
 * academic relationship:
 *
 *   Student -> Enrollment -> AcademicSession -> Class -> Section
 *
 * When an enrollment changes (transfer, promotion, registration approval,
 * withdrawal, class/section move) every one of these views must refresh, or
 * attendance, results and rosters silently show the previous placement.
 */
const ENROLLMENT_DEPENDENT_KEYS = [
  "students",
  "student",
  "roster",
  "attendance",
  "attendance-overview",
  "attendance-history",
  "results",
  "result-sheet",
  "children",
  "academics",
  "class-teachers",
  "promotion-classes",
  "promotion-candidates",
  "finance-summary",
  "announcements",
] as const;

/**
 * Invalidate only the slices the academic modules depend on. Pass any extra
 * exact keys (e.g. the affected student's detail query) as `extra`.
 */
export async function invalidateEnrollmentQueries(
  queryClient: QueryClient,
  extra: QueryKey[] = [],
): Promise<void> {
  await Promise.all([
    ...ENROLLMENT_DEPENDENT_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
    ...extra.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
  ]);
}
