import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/common/page-header";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { getTimetable } from "@/services/school.service";

export const Route = createFileRoute("/_app/timetable")({
  head: () => ({
    meta: [
      { title: "Timetable — Frontline Nexus" },
      {
        name: "description",
        content: "The weekly class timetable with periods, subjects, teachers and rooms.",
      },
      { property: "og:title", content: "Timetable — Frontline Nexus" },
      {
        property: "og:description",
        content: "Weekly class timetable with periods, subjects, teachers and rooms.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: TimetablePage,
});

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

function TimetablePage() {
  const query = useQuery({ queryKey: ["timetable"], queryFn: getTimetable });

  return (
    <div className="space-y-6">
      <PageHeader title="Timetable" description="Your week at a glance, day by day." />

      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {DAYS.map((day) => {
            const slots = query.data.filter((slot) => slot.day === day);
            return (
              <section
                key={day}
                className="fn-panel overflow-hidden"
                aria-labelledby={`day-${day}`}
              >
                <div className="border-b px-5 py-3">
                  <h2 id={`day-${day}`} className="font-semibold">
                    {day}
                  </h2>
                </div>
                {slots.length === 0 ? (
                  <p className="px-5 py-6 text-muted-foreground">No lessons scheduled.</p>
                ) : (
                  <ul className="divide-y">
                    {slots.map((slot) => (
                      <li key={slot.id} className="px-5 py-3">
                        <p className="font-medium">
                          {slot.period} · {slot.subject}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {slot.className} · {slot.teacher} · {slot.room}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
