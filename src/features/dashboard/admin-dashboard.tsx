import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BadgeCheck,
  Banknote,
  CalendarCheck2,
  CircleAlert,
  Users,
  UserCog,
  Wallet,
} from "lucide-react";
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

  const outstanding = finance.data?.outstanding ?? 0;
  const loading =
    wallet.isPending || students.isPending || finance.isPending || attendance.isPending;
  const collected = finance.data?.paid ?? 0;
  const billed = finance.data?.billed ?? collected + outstanding;
  const collectionRate = billed > 0 ? Math.round((collected / billed) * 100) : 0;
  const registerRate =
    attendance.data?.isSchoolDay && attendance.data.total > 0
      ? Math.round((attendance.data.submitted / attendance.data.total) * 100)
      : 0;
  const todayLong = new Date().toLocaleDateString("en-NG", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
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
      <section className="fn-enter relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary via-primary/85 to-[#1d3a5f] p-6 text-primary-foreground sm:p-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-white/10 blur-2xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 right-24 size-56 rounded-full bg-brass/30 blur-2xl"
        />
        <p className="relative text-xs font-semibold uppercase tracking-[0.14em] text-white/70">
          {school?.name} · {todayLong}
        </p>
        <Link
          to="/wallet"
          className="absolute right-5 top-5 inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-semibold tabular-nums backdrop-blur transition hover:bg-white/25 sm:right-7 sm:top-7"
          aria-label={`Wallet balance ${wallet.data ? compactNaira(wallet.data.balance) : "loading"}. Open wallet and billing.`}
        >
          <Wallet className="size-4" aria-hidden="true" />
          {wallet.isPending ? "…" : compactNaira(wallet.data?.balance ?? 0)}
          <span className="text-xs font-normal text-white/70">wallet</span>
          {wallet.data && wallet.data.balance < wallet.data.studentPrice ? (
            <span className="size-2 rounded-full bg-warning" aria-hidden="true" />
          ) : null}
        </Link>
        <h1 className="relative mt-2 font-display text-[1.7rem] font-semibold tracking-[-0.02em] sm:text-[2.1rem]">
          {greeting()}, {user.fullName.split(" ")[0]}.
        </h1>
        <p className="relative mt-2 max-w-xl text-sm text-white/80">
          {school?.currentSession} · {school?.currentTerm} — {attendanceSummary.hint},{" "}
          {collectionRate}% of billed fees collected.
        </p>
        <div className="relative mt-5 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium backdrop-blur">
            <CalendarCheck2 className="size-3.5" aria-hidden="true" />
            {attendance.data?.isSchoolDay ? `Registers ${registerRate}% complete` : "No school today"}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium backdrop-blur">
            <Banknote className="size-3.5" aria-hidden="true" />
            {compactNaira(collected)} collected
          </span>
          {awaitingApproval > 0 ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-warning px-3 py-1.5 text-xs font-semibold text-warning-foreground">
              <CircleAlert className="size-3.5" aria-hidden="true" />
              {awaitingApproval} sheets need approval
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success/90 px-3 py-1.5 text-xs font-semibold text-white">
              <BadgeCheck className="size-3.5" aria-hidden="true" />
              Results up to date
            </span>
          )}
        </div>
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

      {!loading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="fn-panel p-5" aria-labelledby="register-progress">
            <div className="flex items-center justify-between gap-2">
              <h2 id="register-progress" className="font-semibold">
                Today's registers
              </h2>
              <Link
                to="/attendance-overview"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              >
                Open board <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </div>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{attendanceSummary.value}</p>
            <p className="text-sm text-muted-foreground">{attendanceSummary.hint}</p>
            <div
              className="mt-3 h-2.5 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-valuenow={registerRate}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary to-success transition-all"
                style={{ width: `${registerRate}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{registerRate}% of classes submitted</p>
          </section>
          <section className="fn-panel p-5" aria-labelledby="fee-progress">
            <div className="flex items-center justify-between gap-2">
              <h2 id="fee-progress" className="font-semibold">
                Fee collection
              </h2>
              <Link
                to="/finance"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              >
                Open finance <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </div>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{compactNaira(collected)}</p>
            <p className="text-sm text-muted-foreground">
              {compactNaira(outstanding)} still outstanding
            </p>
            <div
              className="mt-3 h-2.5 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-valuenow={collectionRate}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full bg-gradient-to-r from-brass to-success transition-all"
                style={{ width: `${collectionRate}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{collectionRate}% collected</p>
          </section>
        </div>
      ) : null}

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
                Student access {compactNaira(wallet.data.studentPrice)} per student per month.{" "}
                {(access.data?.summary.active ?? 0) === 0
                  ? "No active students — fund the wallet, then activate students one by one."
                  : `${numberFmt(access.data?.summary.active ?? 0)} active · ${compactNaira((access.data?.summary.active ?? 0) * wallet.data.studentPrice)}/mo renewal cost.`}{" "}
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
