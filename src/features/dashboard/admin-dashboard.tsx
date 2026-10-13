import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { StatCard } from "@/components/common/stat-card";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { AttentionList } from "@/features/dashboard/attention-list";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { SetupChecklist } from "@/features/dashboard/setup-checklist";
import { useAuthenticatedSession } from "@/auth/session";
import { compactNaira, greeting, numberFmt } from "@/lib/format";
import { getAttendanceOverview } from "@/services/attendance.service";
import { getFinanceSummary } from "@/services/finance.service";
import { getStaff, getResultSheets } from "@/services/school.service";
import { getWallet, listStudentAccess } from "@/services/wallet.service";
import { listStudents } from "@/services/students.service";

export function AdminDashboard({ readOnly = false }: { readOnly?: boolean }) {
  const { user, school } = useAuthenticatedSession();

  const wallet = useQuery({ queryKey: ["wallet"], queryFn: getWallet });
  const access = useQuery({
    queryKey: ["wallet", "students", "", 1],
    queryFn: () => listStudentAccess(undefined, 1, 1),
  });
  const students = useQuery({
    queryKey: ["students", { pageSize: 1 }],
    queryFn: () => listStudents({ pageSize: 1 }),
  });
  const staff = useQuery({ queryKey: ["staff"], queryFn: getStaff });
  const finance = useQuery({ queryKey: ["finance-summary"], queryFn: getFinanceSummary });
  const results = useQuery({ queryKey: ["results"], queryFn: getResultSheets });
  const attendance = useQuery({
    queryKey: ["attendance-overview"],
    queryFn: () => getAttendanceOverview(),
  });

  if (wallet.isError || students.isError || finance.isError) {
    return (
      <ErrorState
        onRetry={() => void Promise.all([wallet.refetch(), students.refetch(), finance.refetch()])}
      />
    );
  }

  const loading =
    wallet.isPending || students.isPending || finance.isPending || attendance.isPending;
  const outstanding = finance.data?.outstanding ?? 0;
  const awaitingApproval =
    results.data?.filter((r) => r.status === "submitted" || r.status === "under_review").length ??
    0;
  const attendanceSummary = attendance.data
    ? !attendance.data.isSchoolDay
      ? { value: "—", hint: "No register expected today" }
      : attendance.data.total === 0
        ? { value: "—", hint: "No classes are configured for attendance" }
        : {
            value: `${attendance.data.submitted} / ${attendance.data.total}`,
            hint: "Classes have submitted today's register",
          }
    : {
        value: "—",
        hint: attendance.isError ? "Today's attendance could not be loaded" : "Today's registers",
      };

  const attention = [
    attendance.data?.isSchoolDay && attendance.data.total > attendance.data.submitted
      ? {
          id: "registers",
          label: `${attendance.data.total - attendance.data.submitted} class registers are still missing today`,
          to: "/attendance-overview",
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
    wallet.data && wallet.data.balance < wallet.data.studentPrice
      ? {
          id: "wallet",
          label: `Wallet balance ${compactNaira(wallet.data.balance)} is below one student's monthly access`,
          to: "/wallet",
        }
      : null,
    (access.data?.summary.needAttention ?? 0) > 0
      ? {
          id: "activation",
          label: `${access.data?.summary.needAttention} students awaiting activation`,
          to: "/wallet",
        }
      : null,
    (access.data?.summary.expiringSoon ?? 0) > 0
      ? {
          id: "expiring",
          label: `${access.data?.summary.expiringSoon} students' access expires soon`,
          to: "/wallet",
        }
      : null,
  ].filter(Boolean) as { id: string; label: string; to: string }[];

  return (
    <div className="space-y-6">
      <section className="fn-enter border-l-2 border-primary py-1 pl-5">
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
            hint="Enrolled this session"
          />
          <StatCard
            label="Staff"
            value={numberFmt(staff.data?.length ?? 0)}
            hint="Teachers and administrative staff"
          />
          <StatCard
            label="Active paid students"
            value={numberFmt(access.data?.summary.active ?? 0)}
            tone="success"
            hint="Paid access this month"
          />
          <StatCard
            label="Awaiting activation"
            value={numberFmt(access.data?.summary.needAttention ?? 0)}
            tone={(access.data?.summary.needAttention ?? 0) > 0 ? "warning" : "success"}
            hint="Need wallet funding to activate"
          />
          <StatCard
            label="Registers submitted today"
            value={attendanceSummary.value}
            tone={
              attendance.data?.isSchoolDay && attendance.data.total > 0
                ? attendance.data.submitted === attendance.data.total
                  ? "success"
                  : "warning"
                : "default"
            }
            hint={attendanceSummary.hint}
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

      {wallet.data ? (
        <section className="fn-panel p-5" aria-labelledby="wallet-heading">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 id="wallet-heading" className="font-semibold">
                Wallet balance: {compactNaira(wallet.data.balance)}
              </h2>
              <p className="mt-1 text-muted-foreground">
                Student access {compactNaira(wallet.data.studentPrice)} per student per month.
                {wallet.data.balance < wallet.data.studentPrice
                  ? ` Your wallet holds ${compactNaira(wallet.data.balance)}. Fund your wallet to activate students.`
                  : ` You can activate ${Math.floor(wallet.data.balance / wallet.data.studentPrice)} students with your current balance.`}{" "}
                Deposits stay available until a real charge occurs.
              </p>
            </div>
            <Button asChild variant="outline" size="lg" className="shrink-0">
              <Link to="/wallet">Wallet & Billing</Link>
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
