import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Input } from "@/components/ui/input";
import { dateTimeFmt } from "@/lib/format";
import { listAuditEvents } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/security")({
  head: () => ({
    meta: [
      { title: "Security & audit — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Audit trail of privileged actions, sign-in attempts and data exports.",
      },
      { property: "og:title", content: "Security & audit — Frontline Nexus Platform" },
      {
        property: "og:description",
        content: "Audit trail of privileged actions, sign-in attempts and data exports.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformSecurityPage,
});

function PlatformSecurityPage() {
  const [search, setSearch] = useState("");
  const query = useQuery({ queryKey: ["platform", "audit"], queryFn: listAuditEvents });

  const term = search.trim().toLowerCase();
  const events = (query.data ?? []).filter(
    (e) =>
      !term ||
      e.actor.toLowerCase().includes(term) ||
      e.action.toLowerCase().includes(term) ||
      e.target.toLowerCase().includes(term),
  );
  const critical = (query.data ?? []).filter((e) => e.severity === "critical").length;
  const warnings = (query.data ?? []).filter((e) => e.severity === "warning").length;

  return (
    <PermissionGate permission="audit.read">
      <div className="space-y-6">
        <PageHeader
          title="Security & audit"
          description="Every privileged action on the platform is recorded here with the actor, target and originating address."
        />

        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Events (last 24h)" value={query.data?.length ?? 0} />
          <StatCard label="Critical" value={critical} tone={critical ? "danger" : "success"} />
          <StatCard label="Warnings" value={warnings} tone={warnings ? "warning" : "success"} />
        </div>

        <Input
          className="h-11"
          placeholder="Search by actor, action or target"
          aria-label="Search audit events"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : events.length === 0 ? (
          <EmptyState
            title="No matching audit events"
            description="Try a different actor, action or school name."
          />
        ) : (
          <ul className="fn-panel divide-y">
            {events.map((event) => (
              <li key={event.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {event.action} ·{" "}
                    <span className="font-normal text-muted-foreground">{event.target}</span>
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {event.actor} · {event.ip} · {dateTimeFmt(event.createdAt)}
                  </p>
                </div>
                <StatusBadge
                  status={
                    event.severity === "critical"
                      ? "failed"
                      : event.severity === "warning"
                        ? "pending"
                        : "active"
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}
