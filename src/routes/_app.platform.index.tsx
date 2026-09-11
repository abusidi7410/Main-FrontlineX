import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { compactNaira, dateFmt, naira, numberFmt } from "@/lib/format";
import { listPlatformSchools } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/")({
  head: () => ({
    meta: [
      { title: "Platform overview — Frontline Nexus" },
      {
        name: "description",
        content: "Tenant health, revenue and adoption across every school on Frontline Nexus.",
      },
      { property: "og:title", content: "Platform overview — Frontline Nexus" },
      {
        property: "og:description",
        content: "Tenant health, revenue and adoption across every school.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformOverview,
});

function PlatformOverview() {
  const query = useQuery({
    queryKey: ["platform", "schools"],
    queryFn: () => listPlatformSchools(),
  });
  const schools = query.data ?? [];
  const mrr = schools.reduce((sum, s) => sum + s.mrr, 0);
  const students = schools.reduce((sum, s) => sum + s.students, 0);
  const active = schools.filter((s) => s.status === "active").length;
  const atRisk = schools.filter(
    (s) => s.status === "grace" || s.status === "suspended" || s.status === "pending_payment",
  );

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Platform overview"
          description="How Frontline Nexus is performing across every school on the platform."
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                label="Monthly recurring revenue"
                value={naira(mrr)}
                tone="success"
                hint={`${compactNaira(mrr * 12)} annualised`}
              />
              <StatCard
                label="Schools"
                value={numberFmt(schools.length)}
                hint={`${active} active tenants`}
              />
              <StatCard
                label="Students managed"
                value={numberFmt(students)}
                hint="Across all tenants"
              />
              <StatCard
                label="Needs attention"
                value={atRisk.length}
                tone={atRisk.length ? "warning" : "success"}
                hint="Grace, suspended or unpaid"
              />
            </div>

            <section className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="font-medium">Tenants needing attention</h2>
                <Link
                  to="/platform/schools"
                  className="text-sm font-medium text-primary hover:underline"
                >
                  All schools
                </Link>
              </div>
              <ul className="fn-panel divide-y">
                {atRisk.slice(0, 8).map((school) => (
                  <li key={school.id} className="flex flex-wrap items-center gap-3 p-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{school.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {school.state} · {numberFmt(school.students)} students · joined{" "}
                        {dateFmt(school.createdAt)}
                      </p>
                    </div>
                    <span className="tabular-nums text-sm text-muted-foreground">
                      {naira(school.mrr)}/mo
                    </span>
                    <StatusBadge status={school.status} />
                  </li>
                ))}
                {atRisk.length === 0 ? (
                  <li className="p-4 text-sm text-muted-foreground">
                    Every tenant is in good standing.
                  </li>
                ) : null}
              </ul>
            </section>
          </>
        )}
      </div>
    </PermissionGate>
  );
}
