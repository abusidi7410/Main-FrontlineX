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
  const todaySlots = (timetable.data ?? []).filter((slot) => slot.day === today).slice(0, 4);
  const draftSheets = results.data?.filter((r) => r.status === "draft").length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">
          {greeting()}, {user.fullName.split(" ")[0]}.
        </h1>
        <p className="mt-1 text-muted-foreground">
          {school?.name} · {school?.currentTerm}
        </p>
      </div>

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
              <li key={slot.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4">
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
                  className="inline-flex min-h-11 shrink-0 items-center rounded-full bg-primary px-5 font-medium text-primary-foreground shadow-[0_6px_14px_-6px_oklch(0.31_0.02_250/0.55),inset_0_1px_0_oklch(1_0_0/0.1)] transition-all duration-200 hover:-translate-y-px hover:bg-[#273850]"
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
