import type { SubscriptionTier } from "@/types";

/**
 * Central plan configuration. Prices/allowances live here (and later come from
 * the backend `/api/plans` endpoint) — never inline them into components.
 */
export const SUBSCRIPTION_TIERS: SubscriptionTier[] = [
  {
    id: "t100",
    label: "1 – 100 students",
    minStudents: 1,
    maxStudents: 100,
    monthlyPrice: 8000,
    aiCredits: 500,
    storageGb: 5,
    smsAllowance: 200,
    features: ["Core school management", "Attendance & results", "Parent portal", "AI assistant"],
  },
  {
    id: "t200",
    label: "101 – 200 students",
    minStudents: 101,
    maxStudents: 200,
    monthlyPrice: 13000,
    aiCredits: 900,
    storageGb: 10,
    smsAllowance: 400,
    features: ["Everything in 1–100", "Bulk import", "Fee management"],
  },
  {
    id: "t400",
    label: "201 – 400 students",
    minStudents: 201,
    maxStudents: 400,
    monthlyPrice: 19000,
    aiCredits: 1500,
    storageGb: 20,
    smsAllowance: 800,
    features: ["Everything in 101–200", "Timetable conflict detection", "Report cards"],
  },
  {
    id: "t600",
    label: "401 – 600 students",
    minStudents: 401,
    maxStudents: 600,
    monthlyPrice: 25000,
    aiCredits: 2500,
    storageGb: 30,
    smsAllowance: 1200,
    features: ["Everything in 201–400", "Promotion centre", "Advanced reports"],
  },
  {
    id: "t800",
    label: "601 – 800 students",
    minStudents: 601,
    maxStudents: 800,
    monthlyPrice: 31000,
    aiCredits: 3200,
    storageGb: 40,
    smsAllowance: 1600,
    features: ["Everything in 401–600", "Multi-campus arms"],
  },
  {
    id: "t1000",
    label: "801 – 1,000 students",
    minStudents: 801,
    maxStudents: 1000,
    monthlyPrice: 37000,
    aiCredits: 4000,
    storageGb: 60,
    smsAllowance: 2200,
    features: ["Everything in 601–800", "Priority support"],
  },
  {
    id: "t1500",
    label: "1,001 – 1,500 students",
    minStudents: 1001,
    maxStudents: 1500,
    monthlyPrice: 49000,
    aiCredits: 6000,
    storageGb: 90,
    smsAllowance: 3200,
    features: ["Everything in 801–1,000", "Dedicated onboarding"],
  },
  {
    id: "t2000",
    label: "1,501 – 2,000 students",
    minStudents: 1501,
    maxStudents: 2000,
    monthlyPrice: 62000,
    aiCredits: 8000,
    storageGb: 120,
    smsAllowance: 4200,
    features: ["Everything in 1,001–1,500", "Custom domain"],
  },
  {
    id: "tmax",
    label: "2,000+ students",
    minStudents: 2001,
    maxStudents: null,
    monthlyPrice: 78000,
    aiCredits: 12000,
    storageGb: 200,
    smsAllowance: 6000,
    features: ["Everything in 1,501–2,000", "Account manager", "SLA"],
  },
];

export const GROWTH_ALLOWANCE_RATIO = 0.075;

export function tierById(id: string) {
  return SUBSCRIPTION_TIERS.find((t) => t.id === id) ?? SUBSCRIPTION_TIERS[0]!;
}

export function tierForStudentCount(count: number) {
  if (count < (SUBSCRIPTION_TIERS[0]?.minStudents ?? 1)) return SUBSCRIPTION_TIERS[0]!;
  return (
    SUBSCRIPTION_TIERS.find(
      (t) => count >= t.minStudents && (t.maxStudents === null || count <= t.maxStudents),
    ) ?? SUBSCRIPTION_TIERS[SUBSCRIPTION_TIERS.length - 1]!
  );
}
