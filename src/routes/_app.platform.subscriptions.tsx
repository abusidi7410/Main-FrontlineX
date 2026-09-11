import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { SUBSCRIPTION_TIERS } from "@/constants/plans";
import { naira, numberFmt, percent } from "@/lib/format";
import { listPlatformSchools } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/subscriptions")({
  head: () => ({
    meta: [
      { title: "Subscriptions — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Revenue by plan tier, renewals and accounts in grace or arrears.",
      },
      { property: "og:title", content: "Subscriptions — Frontline Nexus Platform" },
      {
        property: "og:description",
        content: "Revenue by plan tier, renewals and accounts in grace or arrears.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformSubscriptionsPage,
});

function PlatformSubscriptionsPage() {
  const query = useQuery({
    queryKey: ["platform", "schools"],
    queryFn: () => listPlatformSchools(),
  });
  const schools = query.data ?? [];
  const mrr = schools.reduce((sum, s) => sum + s.mrr, 0);
  const paying = schools.filter((s) => s.status === "active" || s.status === "grace");
  const arrears = schools.filter((s) => s.status === "grace" || s.status === "pending_payment");

  const byTier = SUBSCRIPTION_TIERS.map((tier) => {
    const members = schools.filter((s) => s.tierId === tier.id);
    return { tier, count: members.length, revenue: members.reduce((sum, s) => sum + s.mrr, 0) };
  }).filter((row) => row.count > 0);

  return (
    <PermissionGate permission="subscription.read">
      <div className="space-y-6">
        <PageHeader
          title="Subscriptions"
          description="Where platform revenue comes from and which accounts need a billing follow-up."
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Monthly recurring revenue" value={naira(mrr)} tone="success" />
              <StatCard
                label="Paying schools"
                value={numberFmt(paying.length)}
                hint={`of ${schools.length} tenants`}
              />
              <StatCard
                label="Average revenue per school"
                value={naira(paying.length ? Math.round(mrr / paying.length) : 0)}
              />
              <StatCard
                label="In arrears"
                value={arrears.length}
                tone={arrears.length ? "warning" : "success"}
                hint="Grace period or unpaid"
              />
            </div>

            <section className="space-y-3">
              <h2 className="font-medium">Revenue by plan</h2>
              <ul className="fn-panel divide-y">
                {byTier.map((row) => (
                  <li key={row.tier.id} className="flex flex-wrap items-center gap-3 p-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{row.tier.label}</p>
                      <p className="text-sm text-muted-foreground">
                        {row.count} school{row.count === 1 ? "" : "s"} ·{" "}
                        {naira(row.tier.monthlyPrice)} per month
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium tabular-nums">{naira(row.revenue)}</p>
                      <p className="text-sm text-muted-foreground">
                        {percent(mrr ? (row.revenue / mrr) * 100 : 0)} of MRR
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </div>
    </PermissionGate>
  );
}
