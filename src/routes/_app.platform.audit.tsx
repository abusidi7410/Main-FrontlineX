import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatCard } from "@/components/common/stat-card";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDebounced } from "@/hooks/use-debounced";
import { dateTimeFmt } from "@/lib/format";
import { listAuditEvents } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/audit")({
  head: () => ({
    meta: [
      { title: "Audit Logs — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Every privileged platform action with actor, target and originating address.",
      },
      { property: "og:title", content: "Audit Logs — Frontline Nexus Platform" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformAuditPage,
});

function PlatformAuditPage() {
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");
  const [action, setAction] = useState("");
  const debouncedSearch = useDebounced(search, 300);
  const debouncedAction = useDebounced(action, 300);

  const query = useQuery({
    queryKey: ["platform", "audit", debouncedSearch, severity, debouncedAction],
    queryFn: () =>
      listAuditEvents({
        search: debouncedSearch,
        severity: severity === "all" ? "" : severity,
        action: debouncedAction,
      }),
  });

  const events = query.data ?? [];
  const critical = events.filter((e) => e.severity === "critical").length;
  const warnings = events.filter((e) => e.severity === "warning").length;

  return (
    <PermissionGate permission="audit.read">
      <div className="space-y-6">
        <PageHeader
          title="Audit Logs"
          description="Actor, action, affected school, timestamp, result and reason for every privileged operation. Secrets and passwords are never stored here."
        />

        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Events" value={events.length} />
          <StatCard label="Critical" value={critical} tone={critical ? "danger" : "success"} />
          <StatCard label="Warnings" value={warnings} tone={warnings ? "warning" : "success"} />
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <Input
            className="h-11"
            placeholder="Search actor, action or target"
            aria-label="Search audit events"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Input
            className="h-11"
            placeholder="Filter by action (e.g. subscription)"
            aria-label="Filter by action"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger className="h-11" aria-label="Filter by severity">
              <SelectValue placeholder="All severities" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All severities</SelectItem>
              <SelectItem value="info">Info</SelectItem>
              <SelectItem value="warning">Warning</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
            </SelectContent>
          </Select>
        </div>

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
              <li key={event.id} className="p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {event.action} ·{" "}
                      <span className="font-normal text-muted-foreground">{event.target}</span>
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {event.actor}
                      {event.school ? ` · ${event.school}` : ""} · {event.ip} ·{" "}
                      {dateTimeFmt(event.createdAt)}
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
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </PermissionGate>
  );
}
