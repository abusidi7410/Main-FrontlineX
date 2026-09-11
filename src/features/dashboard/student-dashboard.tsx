import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { StatCard } from "@/components/common/stat-card";
import { CardsSkeleton } from "@/components/common/states";
import { QuickActions } from "@/features/dashboard/quick-actions";
import { useAuthenticatedSession } from "@/auth/session";
import { greeting, percent } from "@/lib/format";
import { getAnnouncements, getTimetable } from "@/services/school.service";

export function StudentDashboard() {
  const { user, school } = useAuthenticatedSession();
  const timetable = useQuery({ queryKey: ["timetable"], queryFn: getTimetable });
  const announcements = useQuery({ queryKey: ["announcements"], queryFn: getAnnouncements });

  const today = new Date().toLocaleDateString("en-NG", { weekday: "long" });
  const todaySlots = (timetable.data ?? []).filter((slot) => slot.day === today);

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

      {timetable.isPending ? (
        <CardsSkeleton count={3} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Classes today" value={todaySlots.length} hint={today} />
          <StatCard label="My attendance" value={percent(94)} tone="success" hint="This term" />
          <StatCard label="Term average" value={percent(72)} hint="Across all subjects" />
        </div>
      )}

      <QuickActions
        actions={[
          { label: "My timetable", to: "/timetable", icon: "calendar" },
          { label: "My results", to: "/results", icon: "award" },
          { label: "Announcements", to: "/communication", icon: "megaphone" },
          { label: "Study help", to: "/ai", icon: "sparkles" },
        ]}
      />

      <section className="fn-panel overflow-hidden" aria-labelledby="today-heading">
        <div className="border-b px-5 py-4">
          <h2 id="today-heading" className="font-semibold">
            Today's lessons
          </h2>
        </div>
        {todaySlots.length === 0 ? (
          <p className="px-5 py-8 text-center text-muted-foreground">
            No lessons scheduled today. Enjoy your break.
          </p>
        ) : (
          <ul className="divide-y">
            {todaySlots.map((slot) => (
              <li key={slot.id} className="px-5 py-4">
                <p className="font-medium">{slot.subject}</p>
                <p className="text-sm text-muted-foreground">
                  {slot.period} · {slot.room} · {slot.teacher}
                </p>
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

      {announcements.data && announcements.data.length > 0 ? (
        <section className="fn-panel p-5" aria-labelledby="ann-heading">
          <h2 id="ann-heading" className="font-semibold">
            School announcements
          </h2>
          <ul className="mt-3 space-y-3">
            {announcements.data.slice(0, 2).map((item) => (
              <li key={item.id}>
                <p className="font-medium">{item.title}</p>
                <p className="text-muted-foreground">{item.body}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
