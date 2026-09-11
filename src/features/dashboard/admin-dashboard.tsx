import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { StatCard } from "@/components/common/stat-card";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { AttentionList } from "@/features/dashboard/attention-list";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { SetupChecklist } from "@/features/dashboard/setup-checklist";
import { useAuthenticatedSession } from "@/auth/session";
import { tierById } from "@/constants/plans";
import { compactNaira, dateFmt, greeting, numberFmt, percent } from "@/lib/format";
import { listInvoices } from "@/services/finance.service";
import { getStaff, getResultSheets, getSubscription } from "@/services/school.service";
import { listStudents } from "@/services/students.service";

export function AdminDashboard({ readOnly = false }: { readOnly?: boolean }) {
  const { user, school } = useAuthenticatedSession();

  const subscription = useQuery({ queryKey: ["subscription"], queryFn: getSubscription });
  const students = useQuery({
    queryKey: ["students", { pageSize: 1 }],
    queryFn: () => listStudents({ pageSize: 1 }),
  });
  const lowAttendance = useQuery({
    queryKey: ["students", "low-attendance"],
    queryFn: () => listStudents({ pageSize: 500 }),
    select: (page) => page.results.filter((s) => s.attendanceRate < 70).length,
  });
  const staff = useQuery({ queryKey: ["staff"], queryFn: getStaff });
  const invoices = useQuery({ queryKey: ["invoices", ""], queryFn: () => listInvoices() });
  const results = useQuery({ queryKey: ["results"], queryFn: getResultSheets });

  if (subscription.isError || students.isError) {
    return (
      <ErrorState onRetry={() => void Promise.all([subscription.refetch(), students.refetch()])} />
    );
  }

  const loading = subscription.isPending || students.isPending || invoices.isPending;
  const outstanding = invoices.data?.reduce((sum, i) => sum + (i.total - i.paid), 0) ?? 0;
  const awaitingApproval =
    results.data?.filter((r) => r.status === "submitted" || r.status === "under_review").length ??
    0;
  const tier = subscription.data ? tierById(subscription.data.tierId) : null;
  const attendanceAverage = 92;

  const attention = [
    lowAttendance.data
      ? {
          id: "att",
          label: `${lowAttendance.data} students have attendance below 70%`,
          to: "/attendance",
        }
      : null,
    awaitingApproval > 0
      ? {
          id: "res",
          label: `${awaitingApproval} result sheets are awaiting approval`,
          to: "/results",
        }
      : null,
    outstanding > 0
      ? {
          id: "fees",
          label: `${compactNaira(outstanding)} in outstanding school fees`,
          to: "/finance",
          tone: "danger" as const,
        }
      : null,
    subscription.data
      ? {
          id: "sub",
          label: `Subscription renews on ${dateFmt(subscription.data.renewalDate)}`,
          to: "/subscription",
        }
      : null,
  ].filter(Boolean) as { id: string; label: string; to: string }[];

  return (
    <div className="space-y-6">
      <section className="fn-panel fn-enter relative overflow-hidden p-6 sm:p-7">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-20 -top-24 size-64 rounded-full bg-[radial-gradient(circle,oklch(0.31_0.02_250/0.06),transparent_70%)]"
        />
        <span
          aria-hidden="true"
          className="auth-circle-soft pointer-events-none absolute -right-14 -bottom-[5.5rem] size-56"
        />
        <span
          aria-hidden="true"
          className="auth-circle-soft pointer-events-none absolute -left-10 top-0 size-28 opacity-70"
        />
        <p className="text-sm font-medium text-primary">{school?.name}</p>
        <h1 className="mt-1.5 font-display text-[1.625rem] font-semibold tracking-[-0.02em] sm:text-[2rem]">
          {greeting()}, {user.fullName.split(" ")[0]}.
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {school?.currentSession} · {school?.currentTerm}
        </p>
      </section>

      {loading ? (
        <CardsSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Active students"
            value={numberFmt(students.data?.count ?? 0)}
            hint={tier ? `Tier: ${tier.label}` : ""}
          />
          <StatCard
            label="Staff"
            value={numberFmt(staff.data?.length ?? 0)}
            hint="Teachers and administrative staff"
          />
          <StatCard
            label="Attendance this term"
            value={percent(attendanceAverage)}
            tone="success"
            hint="School-wide average"
          />
          <StatCard
            label="Outstanding fees"
            value={compactNaira(outstanding)}
            tone="warning"
            hint="Across current term invoices"
          />
        </div>
      )}

      {!readOnly ? <SetupChecklist /> : null}

      <AttentionList items={attention} />

      <QuickActions
        actions={
          readOnly
            ? [
                { label: "Review results", to: "/results", icon: "award" },
                { label: "View attendance", to: "/attendance", icon: "clipboard" },
                { label: "Create announcement", to: "/communication", icon: "megaphone" },
                { label: "School reports", to: "/reports", icon: "chart" },
                { label: "AI assistant", to: "/ai", icon: "sparkles" },
              ]
            : [
                { label: "Add student", to: "/students/new", icon: "users" },
                { label: "Import students", to: "/students/import", icon: "users" },
                { label: "Add staff", to: "/staff", icon: "userCog" },
                { label: "Take attendance", to: "/attendance", icon: "clipboard" },
                { label: "Record payment", to: "/finance", icon: "wallet" },
                { label: "Enter results", to: "/results", icon: "award" },
                { label: "Create announcement", to: "/communication", icon: "megaphone" },
                { label: "AI assistant", to: "/ai", icon: "sparkles" },
              ]
        }
      />

      {subscription.data && tier ? (
        <section className="fn-panel p-5" aria-labelledby="plan-heading">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 id="plan-heading" className="font-semibold">
                Subscription and AI usage
              </h2>
              <p className="mt-1 text-muted-foreground">
                {numberFmt(subscription.data.activeStudents)} active students · growth allowance{" "}
                {subscription.data.growthAllowance} · AI credits{" "}
                {numberFmt(subscription.data.aiCreditsUsed)} /{" "}
                {numberFmt(subscription.data.aiCreditsTotal)}
              </p>
            </div>
            <Button asChild variant="outline" size="lg" className="shrink-0">
              <Link to="/subscription">Manage subscription</Link>
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
