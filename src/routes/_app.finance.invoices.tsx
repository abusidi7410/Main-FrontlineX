import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Input } from "@/components/ui/input";
import { useDebounced } from "@/hooks/use-debounced";
import { compactNaira, naira } from "@/lib/format";
import { listInvoices } from "@/services/finance.service";

export const Route = createFileRoute("/_app/finance/invoices")({
  head: () => ({
    meta: [
      { title: "Invoices — Frontline Nexus" },
      {
        name: "description",
        content: "Termly fee invoices with balances, part payments and status per student.",
      },
      { property: "og:title", content: "Invoices — Frontline Nexus" },
      {
        property: "og:description",
        content: "Termly fee invoices with balances and status per student.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: InvoicesPage,
});

function InvoicesPage() {
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search, 300);
  const query = useQuery({
    queryKey: ["invoices", debounced],
    queryFn: () => listInvoices(debounced),
  });

  const outstanding = query.data?.reduce((sum, i) => sum + (i.total - i.paid), 0) ?? 0;

  return (
    <PermissionGate permission="finance.read">
      <div className="space-y-6">
        <PageHeader
          title="Invoices"
          description={`Outstanding across the current term: ${compactNaira(outstanding)}.`}
        />

        <Input
          className="h-11"
          placeholder="Search by student name or invoice number"
          aria-label="Search invoices"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        {query.isError ? (
          <ErrorState onRetry={() => void query.refetch()} />
        ) : query.isPending ? (
          <ListSkeleton />
        ) : query.data.length === 0 ? (
          <EmptyState
            title="No invoices found"
            description="Try a different student name or clear your search."
          />
        ) : (
          <div className="fn-panel overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left">
              <caption className="sr-only">Fee invoices</caption>
              <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Student
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Class
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Total
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Paid
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Balance
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {query.data.map((invoice) => (
                  <tr key={invoice.id}>
                    <td className="px-4 py-3">
                      <span className="font-medium">{invoice.studentName}</span>
                      <span className="block text-sm text-muted-foreground">{invoice.term}</span>
                    </td>
                    <td className="px-4 py-3">{invoice.className}</td>
                    <td className="px-4 py-3 tabular-nums">{naira(invoice.total)}</td>
                    <td className="px-4 py-3 tabular-nums">{naira(invoice.paid)}</td>
                    <td className="px-4 py-3 font-medium tabular-nums">
                      {naira(invoice.total - invoice.paid)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={invoice.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PermissionGate>
  );
}
