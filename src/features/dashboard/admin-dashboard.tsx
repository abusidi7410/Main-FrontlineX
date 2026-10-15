import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Banknote, Users, UserCog, Wallet } from "lucide-react";
import { StatCard } from "@/components/common/stat-card";
import { CardsSkeleton, ErrorState } from "@/components/common/states";
import { AttentionList } from "@/features/dashboard/attention-list";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { SetupChecklist } from "@/features/dashboard/setup-checklist";
import { useAuthenticatedSession } from "@/auth/session";
import { compactNaira, greeting, numberFmt, schoolToday } from "@/lib/format";
import { getAttendanceOverview, getTeacherCheckIns } from "@/services/attendance.service";
import { getFinanceSummary } from "@/services/finance.service";
import { getStaff, getResultSheets } from "@/services/school.service";
import { getWallet, listStudentAccess } from "@/services/wallet.service";
import { listStudents } from "@/services/students.service";

export function AdminDashboard({ readOnly = false }: { readOnly?: boolean }) {
  const { user, school, can } = useAuthenticatedSession();

  const canManageTeacherAttendance = can("attendance.staff.manage");

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
  // Counts, not rows: pageSize 1 is enough to read summary.counts for today.
  const teacherCheckins = useQuery({
    queryKey: ["teacher-checkins", "dashboard", schoolToday()],
    queryFn: () => getTeacherCheckIns({ date: schoolToday(), pageSize: 1 }),
    enabled: canManageTeacherAttendance,
  });

  if (wallet.isError || students.isError || finance.isError) {
    return (
      <ErrorState
        onRetry={() => void Promise.all([wallet.refetch(), students.refetch(), finance.refetch()])}
      />
    );
  }

  const outstanding = finance.data?.outstanding ?? 0;
  const loading =
    wallet.isPending || students.isPending || finance.isPending || attendance.isPending;
  const collected = finance.data?.paid ?? 0;
  const billed = finance.data?.billed ?? collected + outstanding;
  const collectionRate = billed > 0 ? Math.round((collected / billed) * 100) : 0;
  const todayLong = new Date().toLocaleDateString("en-NG", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const awaitingApproval =
    results.data?.filter((r) => r.status === "submitted" || r.status === "under_review").length ??
    0;

  const missedCheckins = teacherCheckins.data?.summary.counts["missed"] ?? 0;

  const attention = [
    attendance.data?.isSchoolDay && attendance.data.total > attendance.data.submitted
      ? {
          id: "registers",
          label: `${attendance.data.total - attendance.data.submitted} class registers are still missing today`,
          to: "/attendance-overview",
        }
      : null,
    missedCheckins > 0
      ? {
          id: "teacher-missed",
          label: `${missedCheckins} teacher lesson${missedCheckins === 1 ? "" : "s"} missed check-in today`,
          to: "/teacher-attendance",
          tone: "danger" as const,
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
      <section className="fn-enter relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary via-primary/85 to-[#1d3a5f] p-6 text-primary-foreground sm:p-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-white/10 blur-2xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 right-24 size-56 rounded-full bg-brass/30 blur-2xl"
        />
        <p className="relative max-w-full pr-28 text-xs font-semibold uppercase tracking-[0.14em] text-white/70 sm:pr-40">
          {school?.name} · {todayLong}
        </p>
        <Link
          to="/wallet"
          className="absolute right-4 top-4 inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-2 text-sm font-semibold tabular-nums backdrop-blur transition hover:bg-white/25 sm:right-7 sm:top-7 sm:gap-2 sm:px-4"
          aria-label={`Wallet balance ${wallet.data ? compactNaira(wallet.data.balance) : "loading"}. Open wallet and billing.`}
        >
          <Wallet className="size-4" aria-hidden="true" />
          {wallet.isPending ? "…" : compactNaira(wallet.data?.balance ?? 0)}
          <span className="text-xs font-normal text-white/70">wallet</span>
          {wallet.data && wallet.data.balance < wallet.data.studentPrice ? (
            <span className="size-2 rounded-full bg-warning" aria-hidden="true" />
          ) : null}
        </Link>
        <h1 className="relative mt-2 max-w-full break-words font-display text-[1.55rem] font-semibold leading-tight tracking-[-0.02em] sm:text-[2.1rem]">
          {greeting()}, {user.fullName.split(" ")[0]}.
        </h1>
        <p className="relative mt-2 max-w-xl text-sm text-white/80">
          {school?.currentSession} · {school?.currentTerm} — here's today at a glance.
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
            icon={<Users className="size-5" />}
          />
          <StatCard
            label="Staff"
            value={numberFmt(staff.data?.length ?? 0)}
            hint="Teachers and administrative staff"
            icon={<UserCog className="size-5" />}
          />
          <StatCard
            label="Fee collection"
            value={`${collectionRate}%`}
            tone={collectionRate >= 70 ? "success" : "warning"}
            hint={`${compactNaira(collected)} of ${compactNaira(billed)} billed`}
            icon={<Banknote className="size-5" />}
          />
          <StatCard
            label="Outstanding fees"
            value={compactNaira(outstanding)}
            tone={outstanding > 0 ? "warning" : "success"}
            hint="Across current term invoices"
            icon={<Wallet className="size-5" />}
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
                { label: "School reports", to: "/reports", icon: "chart" },
                { label: "AI assistant", to: "/ai", icon: "sparkles" },
              ]
            : [
                { label: "Take attendance", to: "/attendance", icon: "clipboard" },
                { label: "Record payment", to: "/finance", icon: "wallet" },
                { label: "Enter results", to: "/results", icon: "award" },
                { label: "Add student", to: "/students/new", icon: "users" },
              ]
        }
      />
    </div>
  );
}
