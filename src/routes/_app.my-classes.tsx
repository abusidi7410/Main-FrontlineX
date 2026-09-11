import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Users } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { percent } from "@/lib/format";
import { getTimetable } from "@/services/school.service";
import { listStudents } from "@/services/students.service";

export const Route = createFileRoute("/_app/my-classes")({
  head: () => ({
    meta: [
      { title: "My classes — Frontline Nexus" },
      {
        name: "description",
        content: "The classes you teach, their size, attendance and quick actions.",
      },
      { property: "og:title", content: "My classes — Frontline Nexus" },
      {
        property: "og:description",
        content: "The classes you teach, their size, attendance and quick actions.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: MyClassesPage,
});

function MyClassesPage() {
  const timetable = useQuery({ queryKey: ["timetable"], queryFn: getTimetable });
  const students = useQuery({
    queryKey: ["students", "my-classes"],
    queryFn: () => listStudents({ pageSize: 1000 }),
  });

  const roster = students.data?.results ?? [];
  const classNames = Array.from(
    new Set((timetable.data ?? []).map((slot) => slot.className)),
  ).sort();

  const classes = classNames.map((className) => {
    const members = roster.filter(
      (s) => `${s.className}${s.arm}` === className || s.className === className,
    );
    const subjects = Array.from(
      new Set(
        (timetable.data ?? [])
          .filter((slot) => slot.className === className)
          .map((slot) => slot.subject),
      ),
    );
    const attendance = members.length
      ? members.reduce((sum, s) => sum + s.attendanceRate, 0) / members.length
      : 0;
    return { className, size: members.length, subjects, attendance };
  });

  return (
    <PermissionGate anyOf={["attendance.write", "results.write", "students.read"]}>
      <div className="space-y-6">
        <PageHeader
          title="My classes"
          description="Everything you teach this term, with one tap to mark a register or enter scores."
        />

        {timetable.isError || students.isError ? (
          <ErrorState
            onRetry={() => {
              void timetable.refetch();
              void students.refetch();
            }}
          />
        ) : timetable.isPending || students.isPending ? (
          <ListSkeleton />
        ) : classes.length === 0 ? (
          <EmptyState
            title="No classes assigned yet"
            description="Once your school adds you to the timetable, your classes appear here."
          />
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {classes.map((cls) => (
              <li key={cls.className} className="fn-panel flex flex-col gap-3 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="font-display text-lg font-semibold">{cls.className}</h2>
                    <p className="text-sm text-muted-foreground">
                      {cls.subjects.join(", ") || "No subject assigned"}
                    </p>
                  </div>
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
                    <Users className="size-5" aria-hidden="true" />
                  </span>
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Students</dt>
                    <dd className="font-medium tabular-nums">{cls.size}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Attendance</dt>
                    <dd className="font-medium tabular-nums">{percent(cls.attendance)}</dd>
                  </div>
                </dl>
                <div className="mt-auto flex flex-wrap gap-2">
                  <Button asChild size="sm">
                    <Link to="/attendance">
                      <ClipboardList className="size-4" aria-hidden="true" />
                      Mark register
                    </Link>
                  </Button>
                  <Button asChild size="sm" variant="outline">
                    <Link to="/results">Enter scores</Link>
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}
