import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { dateFmt, dateTimeFmt, numberFmt } from "@/lib/format";
import {
  getPlatformOverview,
  listAllPlatformSchools,
  listAuditEvents,
} from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/activity")({
  head: () => ({
    meta: [
      { title: "Platform Activity — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Registrations, renewals, plan changes and security events across the platform.",
      },
      { property: "og:title", content: "Platform Activity — Frontline Nexus Platform" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformActivityPage,
});

function PlatformActivityPage() {
  const schools = useQuery({
    queryKey: ["platform", "schools"],
    queryFn: () => listAllPlatformSchools(),
  });
  const overview = useQuery({
    queryKey: ["platform", "overview", "30d"],
    queryFn: () => getPlatformOverview("30d"),
  });
  const audit = useQuery({
    queryKey: ["platform", "audit", "recent"],
    queryFn: () => listAuditEvents(),
  });

  const list = schools.data ?? [];
  const recentRegistrations = [...list]
    .sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt))
    .slice(0, 8);

  const events = (audit.data ?? []).slice(0, 30);
  const subscriptions = events.filter((e) => e.action.startsWith("subscription."));
  const complimentary = events.filter((e) => e.action.startsWith("subscription.complimentary"));
  const security = events.filter((e) => e.severity !== "info");

  return (
    <PermissionGate permission="platform.manage">
      <div className="space-y-6">
        <PageHeader
          title="Platform Activity"
          description="Historical events recorded by the backend — registrations, billing changes and security events. This is an event log, not live server monitoring."
        />

        {schools.isError || overview.isError ? (
          <ErrorState
            onRetry={() => {
              void schools.refetch();
              void overview.refetch();
            }}
          />
        ) : schools.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard label="Total schools" value={numberFmt(list.length)} />
              <StatCard
                label="Upcoming renewals (30d)"
                value={numberFmt(overview.data?.upcomingRenewals ?? 0)}
              />
              <StatCard
                label="Complimentary grants (logged)"
                value={numberFmt(complimentary.length)}
                hint="From the audit trail"
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <section className="fn-panel space-y-2 p-5">
                <h2 className="font-medium">Recent registrations</h2>
                <p className="text-sm text-muted-foreground">
                  Newest schools by registration date.
                </p>
                <ul className="divide-y">
                  {recentRegistrations.map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate font-medium">{s.name}</p>
                        <p className="text-xs text-muted-foreground">{s.state}</p>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {dateFmt(s.createdAt)}
                      </span>
                    </li>
                  ))}
                  {recentRegistrations.length === 0 ? (
                    <li className="py-4 text-sm text-muted-foreground">No schools yet.</li>
                  ) : null}
                </ul>
              </section>

              <section className="fn-panel space-y-2 p-5">
                <h2 className="font-medium">Subscription & billing events</h2>
                <p className="text-sm text-muted-foreground">
                  Plan changes, renewals and complimentary-access grants from the audit log.
                </p>
                {audit.isPending ? (
                  <ListSkeleton rows={4} />
                ) : subscriptions.length === 0 ? (
                  <p className="py-4 text-sm text-muted-foreground">
                    No subscription events recorded yet.
                  </p>
                ) : (
                  <ul className="divide-y">
                    {subscriptions.slice(0, 8).map((e) => (
                      <li key={e.id} className="py-2.5">
                        <p className="text-sm font-medium">
                          {e.action} ·{" "}
                          <span className="font-normal text-muted-foreground">{e.target}</span>
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {e.actor} · {dateTimeFmt(e.createdAt)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <section className="fn-panel space-y-2 p-5">
              <h2 className="font-medium">Security events</h2>
              <p className="text-sm text-muted-foreground">
                Warnings and critical events (suspensions, verification mismatches, privileged
                support actions). Full detail lives under{" "}
                <Link to="/platform/audit" className="font-medium text-primary hover:underline">
                  Audit Logs
                </Link>
                .
              </p>
              {audit.isPending ? (
                <ListSkeleton rows={3} />
              ) : security.length === 0 ? (
                <p className="py-2 text-sm text-muted-foreground">No security events recorded.</p>
              ) : (
                <ul className="divide-y">
                  {security.slice(0, 10).map((e) => (
                    <li key={e.id} className="py-2.5">
                      <p className="text-sm font-medium">
                        {e.action} ·{" "}
                        <span className="font-normal text-muted-foreground">{e.target}</span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {e.actor} · {e.ip} · {dateTimeFmt(e.createdAt)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <div className="flex flex-wrap gap-3 text-sm">
              <Link to="/platform/analytics" className="font-medium text-primary hover:underline">
                Growth analytics
              </Link>
              <Link to="/platform/audit" className="font-medium text-primary hover:underline">
                Full audit log
              </Link>
              <Link to="/platform/support" className="font-medium text-primary hover:underline">
                Support queue
              </Link>
            </div>

            <p className="text-xs text-muted-foreground">
              Note: per-school product-usage breakdowns (logins, feature adoption) are derived from
              available login and payment records only. Real-time infrastructure health (CPU,
              latency, error rates) is not instrumented in this deployment, so it is not shown
              rather than estimated.
            </p>
          </>
        )}
      </div>
    </PermissionGate>
  );
}
