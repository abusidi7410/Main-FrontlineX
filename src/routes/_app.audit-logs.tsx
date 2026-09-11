import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ROLE_LABELS } from "@/permissions";
import { dateTimeFmt } from "@/lib/format";
import { getSchoolAuditLogs } from "@/services/school.service";

export const Route = createFileRoute("/_app/audit-logs")({
  head: () => ({
    meta: [
      { title: "Audit logs — Frontline Nexus" },
      {
        name: "description",
        content: "Who did what in your school, with the IP address and time of every action.",
      },
      { property: "og:title", content: "Audit logs — Frontline Nexus" },
      { property: "og:description", content: "Every sensitive action in your school, traced." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AuditLogsPage,
});

function AuditLogsPage() {
  const query = useQuery({ queryKey: ["audit-logs"], queryFn: getSchoolAuditLogs });
  const [search, setSearch] = useState("");

  const term = search.trim().toLowerCase();
  const filtered = (query.data ?? []).filter(
    (event) =>
      !term ||
      event.actor.toLowerCase().includes(term) ||
      event.action.toLowerCase().includes(term) ||
      event.detail.toLowerCase().includes(term) ||
      event.ip.includes(term),
  );

  return (
    <PermissionGate permission="audit.read">
      <div className="space-y-6">
        <PageHeader
          title="Audit logs"
          description="A tamper-evident record of every sensitive action in your school — held for 12 months."
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : (
          <>
            <div className="max-w-sm">
              <Input
                className="h-11"
                placeholder="Search by person, action or IP address"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Filter audit logs"
              />
            </div>
            {filtered.length === 0 ? (
              <EmptyState
                title="No matching events"
                description="Try a different search, or check back later."
              />
            ) : (
              <div className="fn-panel overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[46rem] text-left">
                    <caption className="sr-only">School audit log</caption>
                    <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                      <tr>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Time
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Person
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Action
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          Details
                        </th>
                        <th scope="col" className="px-4 py-3 font-medium">
                          IP address
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {filtered.map((event) => (
                        <tr key={event.id}>
                          <td className="px-4 py-3 whitespace-nowrap text-sm tabular-nums">
                            {dateTimeFmt(event.createdAt)}
                          </td>
                          <td className="px-4 py-3">
                            <p className="font-medium">{event.actor}</p>
                            <p className="text-sm text-muted-foreground">
                              {ROLE_LABELS[event.role]}
                            </p>
                          </td>
                          <td className="px-4 py-3">
                            <Badge variant="outline">{event.action.replace(".", " · ")}</Badge>
                          </td>
                          <td className="px-4 py-3 text-sm">{event.detail}</td>
                          <td className="px-4 py-3 text-sm tabular-nums text-muted-foreground">
                            {event.ip}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </PermissionGate>
  );
}
