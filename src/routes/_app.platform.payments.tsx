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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDebounced } from "@/hooks/use-debounced";
import { dateTimeFmt, naira, numberFmt } from "@/lib/format";
import { listSubscriptionPayments } from "@/services/platform.service";

export const Route = createFileRoute("/_app/platform/payments")({
  head: () => ({
    meta: [
      { title: "Payments & Revenue — Frontline Nexus Platform" },
      {
        name: "description",
        content: "Verified subscription payments and revenue across every school.",
      },
      { property: "og:title", content: "Payments & Revenue — Frontline Nexus Platform" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: PlatformPaymentsPage,
});

const STATUSES = ["all", "success", "pending", "failed", "abandoned"] as const;

function PlatformPaymentsPage() {
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("all");
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search, 300);

  const query = useQuery({
    queryKey: ["platform", "payments", status, debounced],
    queryFn: () =>
      listSubscriptionPayments({
        status: status === "all" ? "" : status,
        search: debounced,
      }),
  });

  const payments = query.data ?? [];
  const verified = payments.filter((p) => p.status === "success");
  const revenue = verified.reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const pending = payments.filter((p) => p.status === "pending").length;
  const failed = payments.filter((p) => p.status === "failed").length;

  return (
    <PermissionGate permission="subscription.read">
      <div className="space-y-6">
        <PageHeader
          title="Payments & Revenue"
          description="Every subscription payment attempt. Only verified gateway payments count as revenue — complimentary access is never recorded here."
        />

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Verified revenue (filter)"
            value={naira(Math.round(revenue))}
            tone="success"
          />
          <StatCard label="Successful payments" value={numberFmt(verified.length)} tone="success" />
          <StatCard
            label="Pending payments"
            value={numberFmt(pending)}
            tone={pending ? "warning" : "success"}
          />
          <StatCard
            label="Failed payments"
            value={numberFmt(failed)}
            tone={failed ? "danger" : "success"}
          />
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            className="h-11"
            placeholder="Search by reference or school name"
            aria-label="Search payments"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select value={status} onValueChange={(v) => setStatus(v as (typeof STATUSES)[number])}>
            <SelectTrigger className="h-11 sm:w-56" aria-label="Filter by payment status">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s === "all" ? "All statuses" : s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : payments.length === 0 ? (
          <EmptyState
            title="No payments match"
            description="Try a different reference, school name or status."
          />
        ) : (
          <div className="fn-panel overflow-x-auto">
            <Table className="min-w-[860px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Reference</TableHead>
                  <TableHead>School</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Paid</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {payments.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-mono text-xs">{p.reference}</TableCell>
                    <TableCell className="font-medium">{p.schoolName}</TableCell>
                    <TableCell className="text-muted-foreground">{p.planName || "—"}</TableCell>
                    <TableCell className="tabular-nums">{naira(Number(p.amount) || 0)}</TableCell>
                    <TableCell className="text-muted-foreground">{p.purpose}</TableCell>
                    <TableCell>
                      <StatusBadge
                        status={
                          p.status === "success"
                            ? "active"
                            : p.status === "pending"
                              ? "pending"
                              : "failed"
                        }
                      />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {p.paidAt ? dateTimeFmt(p.paidAt) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </PermissionGate>
  );
}
