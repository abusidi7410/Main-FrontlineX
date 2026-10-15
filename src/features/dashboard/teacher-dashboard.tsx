import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CalendarClock, WifiOff } from "lucide-react";
import { StatCard } from "@/components/common/stat-card";
import { CardsSkeleton } from "@/components/common/states";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { useAuthenticatedSession } from "@/auth/session";
import { useOfflineQueue } from "@/hooks/use-offline-queue";
import { useOnlineStatus } from "@/hooks/use-online-status";
import { greeting } from "@/lib/format";
import { getResultSheets, getTimetable } from "@/services/school.service";

export function TeacherDashboard() {
  const { user, school } = useAuthenticatedSession();
  const online = useOnlineStatus();
  const { pendingCount, failedCount } = useOfflineQueue();
  const timetable = useQuery({ queryKey: ["timetable"], queryFn: getTimetable });
  const results = useQuery({ queryKey: ["results"], queryFn: getResultSheets });

  const today = new Date().toLocaleDateString("en-NG", { weekday: "long" });
  // `dayName` is the weekday label the API sends; `day` is the Monday-first
  // number and cannot be compared with a date's weekday name.
  const todaySlots = (timetable.data ?? []).filter((slot) => slot.dayName === today).slice(0, 4);
  const draftSheets = results.data?.filter((r) => r.status === "draft").length ?? 0;

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary via-primary/85 to-[#1d3a5f] p-6 text-primary-foreground sm:p-7">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-14 -top-20 size-64 rounded-full bg-white/10 blur-2xl"
        />
        <p className="relative text-xs font-semibold uppercase tracking-[0.14em] text-white/70">
          {school?.name} · {today} · {school?.currentTerm}
        </p>
        <h1 className="relative mt-2 max-w-full break-words font-display text-2xl font-semibold leading-tight sm:text-3xl">
          {greeting()}, {user.fullName.split(" ")[0]}.
        </h1>
        <p className="relative mt-1.5 max-w-lg text-sm text-white/80">
          {todaySlots.length > 0
            ? `You have ${todaySlots.length} ${todaySlots.length === 1 ? "lesson" : "lessons"} on today — first up ${todaySlots[0]?.className} ${todaySlots[0]?.subject}.`
            : "No lessons on your timetable today — a good day to catch up on marking and plans."}
        </p>
        <div className="relative mt-4 flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium backdrop-blur">
            <CalendarClock className="size-3.5" aria-hidden="true" />
            {todaySlots.length} classes today
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium backdrop-blur">
            {draftSheets} draft result {draftSheets === 1 ? "sheet" : "sheets"}
          </span>
          {pendingCount > 0 ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-warning px-3 py-1.5 text-xs font-semibold text-warning-foreground">
              {pendingCount} waiting to sync
            </span>
          ) : null}
        </div>
      </section>

      {!online ? (
        <div
          role="status"
          className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning-soft p-4"
        >
          <WifiOff className="mt-0.5 size-5 shrink-0 text-warning" aria-hidden="true" />
          <p className="text-sm">
            You're offline. You can still take attendance and enter scores — everything is saved on
            this device and syncs automatically when your connection returns.
          </p>
        </div>
      ) : null}

      {timetable.isPending ? (
        <CardsSkeleton count={3} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Classes today"
            value={todaySlots.length}
            hint={today}
            icon={<CalendarClock className="size-5" />}
          />
          <StatCard
            label="Waiting to sync"
            value={pendingCount}
            tone={pendingCount > 0 ? "warning" : "default"}
            hint={
              failedCount > 0
                ? `${failedCount} failed — retry in the sync centre`
                : "All records are up to date"
            }
          />
          <StatCard
            label="Result sheets in draft"
            value={draftSheets}
            hint="Finish and submit for approval"
          />
        </div>
      )}

      <QuickActions
        actions={[
          { label: "Take attendance", to: "/attendance", icon: "clipboard" },
          { label: "Enter results", to: "/results", icon: "award" },
          { label: "Create lesson plan", to: "/lesson-plans", icon: "notebook" },
          { label: "My classes", to: "/my-classes", icon: "users" },
          { label: "Sync centre", to: "/sync", icon: "refresh" },
          { label: "AI assistant", to: "/ai", icon: "sparkles" },
        ]}
      />

      <section className="fn-panel overflow-hidden" aria-labelledby="today-heading">
        <div className="border-b px-5 py-4">
          <h2 id="today-heading" className="font-semibold">
            Today's classes
          </h2>
        </div>
        {todaySlots.length === 0 ? (
          <p className="px-5 py-8 text-center text-muted-foreground">
            You have no scheduled classes today. Check your full timetable for the week.
          </p>
        ) : (
          <ul className="divide-y">
            {todaySlots.map((slot) => (
              <li key={slot.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4 hover:bg-muted/40">
                <span
                  aria-hidden="true"
                  className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary-soft font-semibold text-primary"
                >
                  {(slot.period || "?").slice(0, 2).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {slot.className} · {slot.subject}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {slot.period} · {slot.room}
                  </p>
                </div>
                <Link
                  to="/attendance"
                  className="inline-flex min-h-11 shrink-0 items-center rounded-full bg-primary px-5 font-medium text-primary-foreground shadow-[0_6px_14px_-6px_oklch(0.31_0.02_250/0.55),inset_0_1px_0_oklch(1_0_0/0.1)] transition-all duration-200 hover:-translate-y-px hover:bg-primary/90"
                >
                  Take attendance
                </Link>
              </li>
            ))}
          </ul>
        )}
        <div className="border-t px-5 py-3">
          <Link to="/timetable" className="font-medium text-primary hover:underline">
            View full timetable
          </Link>
        </div>
      </section>
    </div>
  );
}
