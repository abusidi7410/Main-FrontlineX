import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Progress } from "@/components/ui/progress";
import { naira, numberFmt, percent } from "@/lib/format";
import { listPlatformSchools } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/analytics")({
  head: () => ({
    meta: [
      { title: "Analytics — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Growth, regional spread and product adoption across Frontline Nexus schools.",
      },
      { property: "og:title", content: "Analytics — Frontline Nexus Platform" },
      {
        property: "og:description",
        content: "Growth, regional spread and product adoption across schools.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformAnalyticsPage,
});

const ADOPTION = [
  { feature: "Attendance register", rate: 92 },
  { feature: "Results & report cards", rate: 84 },
  { feature: "Fee management", rate: 71 },
  { feature: "Parent portal", rate: 63 },
  { feature: "AI assistant", rate: 48 },
  { feature: "Offline teacher app", rate: 39 },
];

function PlatformAnalyticsPage() {
  const query = useQuery({
    queryKey: ["platform", "schools"],
    queryFn: () => listPlatformSchools(),
  });
  const schools = query.data ?? [];
  const students = schools.reduce((sum, s) => sum + s.students, 0);

  const byState = Object.entries(
    schools.reduce<Record<string, { count: number; students: number }>>((acc, s) => {
      const row = acc[s.state] ?? { count: 0, students: 0 };
      acc[s.state] = { count: row.count + 1, students: row.students + s.students };
      return acc;
    }, {}),
  ).sort((a, b) => b[1].count - a[1].count);

  const newThisQuarter = schools.filter(
    (s) => Date.now() - new Date(s.createdAt).getTime() < 92 * 24 * 60 * 60 * 1000,
  ).length;

  return (
    <PermissionGate permission="reports.read">
      <div className="space-y-6">
        <PageHeader
          title="Analytics"
          description="Where Frontline Nexus is growing and which features schools actually use."
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Schools" value={numberFmt(schools.length)} />
              <StatCard label="New this quarter" value={numberFmt(newThisQuarter)} tone="success" />
              <StatCard label="Students managed" value={numberFmt(students)} />
              <StatCard
                label="Average school size"
                value={numberFmt(schools.length ? Math.round(students / schools.length) : 0)}
                hint="Students per school"
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="fn-panel space-y-3 p-5">
                <h2 className="font-medium">Schools by state</h2>
                <ul className="space-y-3">
                  {byState.slice(0, 8).map(([state, row]) => (
                    <li key={state}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>{state}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {row.count} · {numberFmt(row.students)} students
                        </span>
                      </div>
                      <Progress
                        value={schools.length ? (row.count / schools.length) * 100 : 0}
                        aria-label={`${state} share of schools`}
                      />
                    </li>
                  ))}
                </ul>
              </section>

              <section className="fn-panel space-y-3 p-5">
                <h2 className="font-medium">Feature adoption</h2>
                <ul className="space-y-3">
                  {ADOPTION.map((row) => (
                    <li key={row.feature}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>{row.feature}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {percent(row.rate)}
                        </span>
                      </div>
                      <Progress value={row.rate} aria-label={`${row.feature} adoption`} />
                    </li>
                  ))}
                </ul>
              </section>
            </div>

            <p className="text-sm text-muted-foreground">
              Platform revenue this month:{" "}
              <span className="font-medium">{naira(schools.reduce((s, x) => s + x.mrr, 0))}</span>
            </p>
          </>
        )}
      </div>
    </PermissionGate>
  );
}
