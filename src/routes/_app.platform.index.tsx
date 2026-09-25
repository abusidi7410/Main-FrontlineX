import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Building2, CircleDollarSign, TriangleAlert, UsersRound } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
  const mrr = schools.reduce((sum, school) => sum + school.mrr, 0);
  const students = schools.reduce((sum, school) => sum + school.students, 0);
  const active = schools.filter((school) => school.status === "active").length;
  const atRisk = schools.filter(
    (school) =>
      school.status === "grace" ||
      school.status === "suspended" ||
      school.status === "pending_payment",
  );
  const activeRate = schools.length ? Math.round((active / schools.length) * 100) : 0;

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
                icon={<CircleDollarSign className="size-4" />}
              />
              <StatCard
                label="Schools"
                value={numberFmt(schools.length)}
                hint={`${active} active tenants`}
                icon={<Building2 className="size-4" />}
              />
              <StatCard
                label="Students managed"
                value={numberFmt(students)}
                hint="Across all tenants"
                icon={<UsersRound className="size-4" />}
              />
              <StatCard
                label="Needs attention"
                value={atRisk.length}
                tone={atRisk.length ? "warning" : "success"}
                hint={`${activeRate}% of tenants active`}
                icon={<TriangleAlert className="size-4" />}
              />
            </div>

            <section className="space-y-4" aria-labelledby="tenant-health-heading">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-primary">Tenant health</p>
                  <h2 id="tenant-health-heading" className="mt-1">
                    Tenants needing attention
                  </h2>
                </div>
                <Link
                  to="/platform/schools"
                  className="text-sm font-semibold text-primary transition-colors hover:text-primary/80 hover:underline"
                >
                  View all schools
                </Link>
              </div>

              <Card className="overflow-hidden">
                <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-border/60 bg-muted/20 px-5 py-4">
                  <CardTitle className="text-base">Follow-up queue</CardTitle>
                  <span className="rounded-full bg-warning-soft px-2.5 py-1 text-xs font-semibold text-warning">
                    {atRisk.length} {atRisk.length === 1 ? "tenant" : "tenants"}
                  </span>
                </CardHeader>
                <CardContent className="p-0">
                  {atRisk.length ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>School</TableHead>
                          <TableHead>Students</TableHead>
                          <TableHead>MRR</TableHead>
                          <TableHead>Joined</TableHead>
                          <TableHead>Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {atRisk.slice(0, 8).map((school) => (
                          <TableRow key={school.id}>
                            <TableCell>
                              <div className="min-w-[12rem]">
                                <p className="font-semibold text-foreground">{school.name}</p>
                                <p className="mt-0.5 text-xs text-muted-foreground">
                                  {school.state}
                                </p>
                              </div>
                            </TableCell>
                            <TableCell className="tabular-nums text-muted-foreground">
                              {numberFmt(school.students)}
                            </TableCell>
                            <TableCell className="whitespace-nowrap font-medium tabular-nums">
                              {naira(school.mrr)}/mo
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-muted-foreground">
                              {dateFmt(school.createdAt)}
                            </TableCell>
                            <TableCell>
                              <StatusBadge status={school.status} />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
                      <div className="grid size-11 place-items-center rounded-full bg-success-soft text-success">
                        <Building2 className="size-5" aria-hidden="true" />
                      </div>
                      <p className="font-semibold text-foreground">
                        All tenants are in good standing
                      </p>
                      <p className="max-w-md text-sm text-muted-foreground">
                        Grace, suspended and unpaid schools will appear here for follow-up.
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </section>
          </>
        )}
      </div>
    </PermissionGate>
  );
}
